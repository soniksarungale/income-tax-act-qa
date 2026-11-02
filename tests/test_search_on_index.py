"""Retrieval checks against the real index. Skipped unless the Act has been ingested
(python -m taxqa.ingest) and Postgres is running."""

import pytest

psycopg = pytest.importorskip("psycopg")


def _index_ready() -> bool:
    try:
        from taxqa.db import connection

        with connection() as conn:
            row = conn.execute("SELECT count(*) AS n FROM chunks WHERE embedding IS NOT NULL").fetchone()
        return row["n"] > 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _index_ready(), reason="index not loaded")

CASES = [
    # The example question from the assignment brief.
    ("I own a residential property that I have rented out. Can I claim a 30% deduction on the annual "
     "value of the property? I also have a housing loan on this property. Can I claim a deduction for "
     "the interest paid on the loan? Which sections of the Income-tax Act apply?", {"23", "24"}),
    ("Is tuition fees paid for children deductible?", {"80C"}),
    ("What is the due date for filing return of income for a company?", {"139"}),
    ("Who is a resident in India?", {"6"}),
    ("What is the penalty for not deducting TDS?", {"271C"}),
    ("Is HRA exempt?", {"10"}),
    ("What is the tax on long-term capital gains from sale of listed equity shares?", {"112A"}),
]


@pytest.mark.parametrize("question,sections", CASES)
def test_expected_sections_are_retrieved(question, sections):
    from taxqa.search import search

    found = {h.number for h in search(question)}
    assert sections <= found, f"missing {sections - found}; got {found}"


def test_named_section_returns_its_own_chunks_first():
    from taxqa.search import search

    hits = search("Explain section 80D")
    assert all(h.number == "80D" for h in hits[:8])
    assert any(h.ref == "Section 80D(1)" for h in hits)


def test_tuition_fees_clause_ranks_first():
    from taxqa.search import search

    assert search("Is tuition fees paid for children deductible?")[0].ref == "Section 80C(2)(xvii)"


def _extracts(question):
    from taxqa.search import expand, search, section_refs

    return expand(search(question), {r.number for r in section_refs(question)})


def test_short_provisions_are_given_whole():
    refs = {e.ref for e in _extracts(CASES[0][0])}
    assert {"Section 24(a)", "Section 24(b)", "Section 24(b), second proviso", "Section 24(b), fourth proviso"} <= refs


def test_long_provisions_bring_the_text_a_hit_depends_on():
    refs = {e.ref for e in _extracts("Is tuition fees paid for children deductible?")}
    # 80C(2) introduces clause (xvii); 80C(1) sets the limit; 80C(4)(c) says which children.
    assert {"Section 80C(1)", "Section 80C(2)", "Section 80C(2)(xvii)", "Section 80C(4)(c)"} <= refs
