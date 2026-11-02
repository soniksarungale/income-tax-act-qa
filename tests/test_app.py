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

    monkeypatch.setattr(app_module, "answer", fake_answer)
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
