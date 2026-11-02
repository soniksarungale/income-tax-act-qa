import json

import pytest

from taxqa import answer as answer_module
from taxqa import llm
from taxqa.answer import answer, build_prompt, parse_reply, quote_found, verify
from taxqa.search import Hit


def hit(chunk_id, ref, text, provision_id=1, heading="Deductions from income from house property.", page=92):
    return Hit(chunk_id, ref, ref.split()[1].split("(")[0], heading, page, page, text, f"{ref} context",
               [], provision_id, [])


HITS = [
    hit(1, "Section 24", "Income chargeable under the head “Income from house property” shall be "
        "computed after making the following deductions, namely:—"),
    hit(2, "Section 24(a)", "(a) a sum equal to thirty per cent of the annual value;"),
    hit(3, "Section 24(b)", "(b) where the property has been acquired, constructed, repaired, renewed or "
        "reconstructed with borrowed capital, the amount of any interest payable on such capital:"),
]


def claim(statement, sources, quote):
    return {"statement": statement, "sources": sources, "quote": quote}


def test_verified_claim():
    [c] = verify([claim("30% of annual value is deducted.", ["S2"], "a sum equal to thirty per cent")], HITS)
    assert c.verified and c.citations[0].ref == "Section 24(a)" and c.citations[0].page_start == 92


def test_quote_must_come_from_the_cited_extract():
    [c] = verify([claim("Interest is deductible.", ["S2"], "the amount of any interest payable")], HITS)
    assert not c.verified and c.problem == "quote not found in the cited text"


def test_unknown_or_missing_sources_are_flagged():
    a, b = verify([claim("x", ["S9"], "a sum equal to thirty per cent"), claim("y", [], "anything at all here")], HITS)
    assert a.problem == "cites an extract that was not provided" and not a.verified
    assert b.problem == "no source cited"


def test_quotes_tolerate_typography_but_not_rewording():
    sources = [HITS[0]]
    assert quote_found('the head "Income from house property" shall be computed', sources)
    assert quote_found("Income chargeable ... the following deductions", sources)
    assert not quote_found("Income chargeable under the head salaries", sources)
    assert not quote_found("Income chargeable", sources)  # too short to identify a passage


def test_quote_from_the_context_does_not_count():
    assert not quote_found("Section 24(a) context", [HITS[1]])


def test_parse_reply_accepts_fenced_json():
    assert parse_reply('Here you go:\n```json\n{"answerable": false}\n```') == {"answerable": False}
    with pytest.raises(ValueError):
        parse_reply("I cannot answer that.")


def test_prompt_groups_extracts_under_their_provision():
    prompt = build_prompt("Can I deduct interest?", HITS)
    assert prompt.count("## Section 24: Deductions from income from house property.") == 1
    assert "[S3] Section 24(b) (page 92)" in prompt
    assert prompt.endswith("Question: Can I deduct interest?")


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr(answer_module, "document", lambda: ("Income-tax Act, 1961", "As amended by Finance Act, 2026"))
    monkeypatch.setattr(answer_module, "search", lambda q: HITS)
    monkeypatch.setattr(answer_module, "expand", lambda hits, named: hits)
    replies = []

    def complete(system, prompt):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return llm.Completion(reply if isinstance(reply, str) else json.dumps(reply), "test-model", 5)

    monkeypatch.setattr(llm, "complete", complete)
    return replies


def test_answered(pipeline):
    pipeline.append({"answerable": True, "not_covered": "",
                     "claims": [claim("30% is deducted.", ["S2"], "a sum equal to thirty per cent of the annual value")]})
    a = answer("Can I deduct 30%?")
    assert a.status == "answered" and a.document == "Income-tax Act, 1961" and a.model == "test-model"


def test_partial_when_a_claim_fails_verification(pipeline):
    pipeline.append({"answerable": True, "claims": [
        claim("30% is deducted.", ["S2"], "a sum equal to thirty per cent"),
        claim("The limit is 2 lakh.", ["S3"], "shall not exceed two lakh rupees")]})
    a = answer("q")
    assert a.status == "partial" and [c.verified for c in a.claims] == [True, False]


def test_reported_gaps_do_not_make_a_verified_answer_partial(pipeline):
    pipeline.append({"answerable": True, "not_covered": "Whether an HUF qualifies.",
                     "claims": [claim("30% is deducted.", ["S2"], "a sum equal to thirty per cent")]})
    a = answer("q")
    assert a.status == "answered" and a.not_covered


def test_refused_when_model_says_unanswerable(pipeline):
    pipeline.append({"answerable": False, "claims": [], "not_covered": "GST is not in the Income-tax Act."})
    a = answer("What is the GST rate?")
    assert a.status == "refused" and a.claims == [] and "GST" in a.not_covered


def test_refused_when_nothing_verifies(pipeline):
    pipeline.append({"answerable": True, "claims": [claim("Rate is 18%.", ["S1"], "rate of eighteen per cent")]})
    a = answer("q")
    assert a.status == "refused" and a.claims[0].problem == "quote not found in the cited text"


def test_retries_once_on_unreadable_reply(pipeline):
    pipeline.extend(["not json", {"answerable": False, "claims": []}])
    assert answer("q").status == "refused"
    pipeline.extend(["not json", "still not json"])
    assert answer("q").status == "error"


def test_provider_errors_are_reported(pipeline):
    pipeline.append(llm.LLMBusy("Too many questions are queued"))
    a = answer("q")
    assert a.status == "error" and "queued" in a.message
