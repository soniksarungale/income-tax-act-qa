from taxqa.parser import Line, Marker, Span, _Builder, join_lines, place, render_ref

MARGIN = 27.6


def line(text, x=MARGIN, page=1, y=100.0, bold_prefix="", italic=False, all_bold=False):
    spans = []
    if bold_prefix:
        spans.append(Span(bold_prefix, x, True, False))
    if text:
        spans.append(Span(text, x + (20 if bold_prefix else 0), all_bold, italic))
    return Line(page, y, spans)


def build(lines, markers=()):
    b = _Builder(list(markers))
    for i, ln in enumerate(lines):
        if ln.y == 100.0:
            ln.y = 100.0 + i * 10
        b.feed(ln)
    return b.finish()


def refs(provision):
    return [c.ref for c in provision.chunks]


def test_section_with_clauses_and_provisos():
    [p] = build([
        line("Deductions from income from house property.", all_bold=True),
        line(" Income chargeable under the head shall be computed after making the following deductions, namely:—",
             bold_prefix="24."),
        line("(a) a sum equal to thirty per cent of the annual value;", x=40.8),
        line("(b) where the property has been acquired with borrowed capital, the amount of any interest payable on",
             x=40.8),
        line("such capital:", x=55.2),
        line(" that the deduction shall not exceed thirty thousand rupees :", x=52, bold_prefix="Provided"),
        line(" further that the deduction shall not exceed two lakh rupees.", x=52, bold_prefix="Provided"),
    ])
    assert p.number == "24"
    assert p.heading == "Deductions from income from house property."
    assert refs(p) == [
        "Section 24",
        "Section 24(a)",
        "Section 24(b)",
        "Section 24(b), first proviso",
        "Section 24(b), second proviso",
    ]
    assert p.chunks[2].text.endswith("interest payable on such capital:")


def test_closing_words_return_to_subsection():
    [p] = build([
        line(" (1) Every person,—", bold_prefix="139."),
        line("(a) being a company or a firm; or", x=41),
        line("(b) being a person other than a company or a firm,", x=41),
        line("shall, on or before the due date, furnish a return of his income."),
    ])
    assert refs(p) == ["Section 139(1)", "Section 139(1)(a)", "Section 139(1)(b)", "Section 139(1)"]


def test_cross_reference_on_a_wrapped_line_is_not_a_new_subsection():
    [p] = build([
        line(" (1) The deduction referred to in sub-section", bold_prefix="23."),
        line("(2) of section 23 shall be allowed."),
        line("(2) The annual value shall be taken to be nil."),
    ])
    assert refs(p) == ["Section 23(1)", "Section 23(2)"]
    assert "(2) of section 23 shall be allowed" in p.chunks[0].text


def test_footnotes_are_not_indexed_even_when_they_quote_old_text():
    [p] = build([
        line(" (1) Every person shall furnish a return.", bold_prefix="139."),
        line("54. Sub. by Act No. 4 of 2026, w.e.f. 1-3-2026. Prior to its substitution, Explanation 2 read as under:",
             x=29.7, y=700),
        line("'Explanation 2.—In this sub-section, \"due date\" means the 31st day of July.'", x=41.5, page=2, y=60),
    ])
    assert "due date" not in p.text
    assert p.notes["54"].startswith("Sub. by Act No. 4 of 2026")


def test_amendment_marker_is_attached_to_the_line_it_marks():
    [p] = build(
        [
            line(" (1) Every person shall furnish a return.", bold_prefix="139.", y=100),
            line("(2) A revised return may be furnished.", y=112),
            line("54. Sub. by Act No. 4 of 2026, w.e.f. 1-3-2026.", x=29.7, y=700),
        ],
        markers=[Marker(page=1, y=106.0, label="54")],
    )
    assert p.chunks[0].amended_by == []
    assert p.chunks[1].amended_by == ["Sub. by Act No. 4 of 2026, w.e.f. 1-3-2026."]


def test_omitted_sections_are_recorded():
    provisions = build([
        line(" Some text.", bold_prefix="75."),
        line("Omitted by the Finance Act, 1992, w.e.f. 1-4-1993", bold_prefix="76. & 77. ", italic=True),
    ])
    omitted = provisions[-1]
    assert omitted.omitted and omitted.number == "76 and 77"


def test_section_printed_out_of_place_gets_its_chapter_back():
    provisions = build([
        line("CHAPTER XIV", x=270, all_bold=True, italic=True),
        line("PROCEDURE FOR ASSESSMENT", x=232, all_bold=True),
        line(" Every person shall furnish a return.", bold_prefix="139."),
        line("CHAPTER XIII", x=270, all_bold=True, italic=True),
        line("INCOME-TAX AUTHORITIES", x=232, all_bold=True),
        line(" The authorities are as follows.", bold_prefix="116."),
        line(" Interest for default.", bold_prefix="138."),
        line(" Quoting of permanent account number.", bold_prefix="139A."),
    ])
    assert [p.number for p in provisions] == ["116", "138", "139", "139A"]
    by_number = {p.number: p for p in provisions}
    assert by_number["138"].chapter == "XIII"
    assert by_number["139A"].chapter == "XIV"


def test_only_first_items_open_a_list():
    assert place([], "xvi") is None
    assert place(["12"], "c") is None
    assert place(["12"], "2") is None


def test_place_sequences():
    p = place([], "1")
    p = place(p, "a")
    p = place(p, "i")
    assert p == ["11", "2a", "3i"]
    assert place(p, "ii") == ["11", "2a", "3ii"]
    assert place(p, "b") == ["11", "2b"]
    assert place(p, "ia") == ["11", "2a", "3ia"]
    assert place(["11", "2h"], "i") == ["11", "2i"]  # (i) after (h) is a letter
    assert place(["11", "2a"], "i") == ["11", "2a", "3i"]  # (i) after (a) opens sub-clauses
    assert place(["11", "2b"], "ba") == ["11", "2ba"]
    assert place(["12", "3xvi"], "a") == ["12", "3xvi", "2a"]
    assert place(["12", "3xvi", "2b"], "xvii") == ["12", "3xvii"]
    assert place(["12", "3xviii"], "1") == ["12", "3xviii", "11"]  # numbered items inside a clause
    assert place(["12", "3xviii", "13"], "4") == ["12", "3xviii", "14"]


def test_render_ref():
    assert render_ref("Section 24", ("2b", "~first proviso")) == "Section 24(b), first proviso"
    assert render_ref("Section 2", ("124", "3iia")) == "Section 2(24)(iia)"
    assert render_ref("Section 50AA", ("~Explanation", "3i")) == "Section 50AA, Explanation (i)"


def test_compounds_split_at_line_end_are_rejoined():
    rows = [Line(1, 10, [Span("referred to in sub-", 40, False, False)]),
            Line(1, 20, [Span("section (2) and income-", 40, False, False)]),
            Line(1, 30, [Span("tax payable — namely", 40, False, False)])]
    assert join_lines(rows) == "referred to in sub-section (2) and income-tax payable — namely"
