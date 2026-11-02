"""Checks against the real 2026 PDF. Skipped when the PDF has not been downloaded."""

import pytest

from taxqa.config import settings
from taxqa.parser import parse_pdf

pytestmark = pytest.mark.skipif(not settings.act_pdf_path.exists(), reason="Act PDF not downloaded")


@pytest.fixture(scope="module")
def act():
    return parse_pdf(settings.act_pdf_path)


@pytest.fixture(scope="module")
def by_number(act):
    return {p.number: p for p in act.provisions}


def test_edition(act):
    assert act.edition == "Finance Act, 2026"
    assert act.page_count == 1117


def test_section_24_matches_the_statute(by_number):
    s24 = by_number["24"]
    assert s24.heading == "Deductions from income from house property."
    assert s24.chapter == "IV"
    assert s24.part == "C.—Income from house property"
    refs = {c.ref: c for c in s24.chunks}
    assert "thirty per cent of the annual value" in refs["Section 24(a)"].text
    assert "borrowed capital" in refs["Section 24(b)"].text
    assert refs["Section 24(a)"].page_start == 92


def test_section_139_keeps_its_pdf_pages_and_chapter(by_number):
    s139 = by_number["139"]
    assert (s139.page_start, s139.chapter) == (1, "XIV")
    assert by_number["139A"].chapter == "XIV"
    assert by_number["138"].chapter == "XIII"


def test_substituted_text_quoted_in_footnotes_is_not_indexed(act):
    for p in act.provisions:
        for c in p.chunks:
            assert "Prior to its substitution" not in c.text, c.ref
            assert "read as under" not in c.text, c.ref


def test_long_lists_are_split_per_clause(by_number):
    refs = {c.ref for c in by_number["80C"].chunks}
    for clause in ["i", "ii", "xvii", "xviii", "xxv"]:
        assert f"Section 80C(2)({clause})" in refs


def test_omitted_sections_and_schedules(act, by_number):
    assert by_number["76 and 77"].omitted
    schedules = [p for p in act.provisions if p.kind == "schedule" and ", rule" not in p.number]
    assert len(schedules) == 14


def test_chunks_fit_the_embedding_window(act):
    assert max(len(c.text) for p in act.provisions for c in p.chunks) <= 1800
