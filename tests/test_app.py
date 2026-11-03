import json

import pytest
from fastapi.testclient import TestClient

from taxqa import app as app_module
from taxqa.answer import Answer, Citation, Claim
from taxqa.search import Hit


def hit(i, ref, similarity=0.0, sources=()):
    return Hit(i, ref, "24", "Deductions from income from house property.", 92, 92, f"text {i}", "", [], 1, [],
               similarity=similarity, sources=list(sources))


@pytest.fixture
def client(monkeypatch):
    retrieved = [hit(2, "Section 24(a)", 0.78, ("vector", "keyword"))]

    def fake_answer(question):
        return Answer(question, "answered", document="Income-tax Act, 1961", edition="As amended by Finance Act, 2026",
                      claims=[Claim("30% is deducted.", "a sum equal to thirty per cent",
                                    [Citation("S2", "Section 24(a)", "", 92, 92)], True)],
                      sources=[hit(1, "Section 24"), retrieved[0], hit(3, "Section 24(b)")], retrieved=retrieved,
                      model="test-model")

    def fake_events(question):
        yield {"type": "retrieved", "extracts": 3, "sections": ["Section 24"], "ms": 5}
        yield {"type": "draft", "field": "statement", "claim": 0, "text": "30% is "}
        yield {"type": "draft", "field": "statement", "claim": 0, "text": "deducted."}
        yield {"type": "done", "answer": fake_answer(question)}

    monkeypatch.setattr(app_module, "answer", fake_answer)
    monkeypatch.setattr(app_module, "answer_events", fake_events)
    monkeypatch.setattr(app_module, "_requests", type(app_module._requests)(app_module._requests.default_factory))
    return TestClient(app_module.app)


def test_ask_returns_claims_confidence_and_only_cited_sources(client):
    res = client.post("/api/ask", json={"question": "Can I deduct 30%?"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "answered"
    assert data["claims"][0]["citations"][0] == {"label": "S2", "ref": "Section 24(a)", "heading": "",
                                                 "document": "Income-tax Act, 1961", "page_start": 92, "page_end": 92}
    assert [s["ref"] for s in data["sources"]] == ["Section 24(a)"]
    assert data["extracts_considered"] == 3
    assert data["confidence"]["label"] == "high"


def test_question_length_is_validated(client):
    assert client.post("/api/ask", json={"question": "x"}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 1001}).status_code == 422


def test_rate_limit_per_client(client, monkeypatch):
    monkeypatch.setattr(app_module, "RATE_LIMIT", 2)
    codes = [client.post("/api/ask", json={"question": "Is HRA exempt?"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_stream_sends_draft_pieces_then_the_verified_answer(client):
    res = client.post("/api/ask/stream", json={"question": "Can I deduct 30%?"})
    assert res.status_code == 200 and res.headers["content-type"].startswith("application/x-ndjson")
    assert res.headers["x-accel-buffering"] == "no"
    events = [json.loads(line) for line in res.text.splitlines()]
    assert [e["type"] for e in events] == ["retrieved", "draft", "draft", "done"]
    done = events[-1]["answer"]
    assert done["status"] == "answered" and done["confidence"]["label"] == "high"


def test_stream_is_rate_limited_and_validated(client, monkeypatch):
    assert client.post("/api/ask/stream", json={"question": "x"}).status_code == 422
    monkeypatch.setattr(app_module, "RATE_LIMIT", 1)
    assert client.post("/api/ask/stream", json={"question": "Is HRA exempt?"}).status_code == 200
    assert client.post("/api/ask/stream", json={"question": "Is HRA exempt?"}).status_code == 429


def test_page_and_assets_are_revalidated_after_a_deploy(client):
    for path in ("/", "/static/app.js", "/static/style.css"):
        res = client.get(path)
        assert res.status_code == 200 and res.headers["cache-control"] == "no-cache"
