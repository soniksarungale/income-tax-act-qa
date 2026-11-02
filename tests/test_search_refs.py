from taxqa.search import expand_abbreviations, section_refs


def refs(q):
    return [(r.number, r.path) for r in section_refs(q)]


def test_explicit_section_references():
    assert refs("Is interest deductible under section 24(b)?") == [("24", ["b"])]
    assert refs("What does sec. 139(1) say?") == [("139", ["1"])]
    assert refs("Deduction u/s 80C and s. 80D") == [("80C", []), ("80D", [])]
    assert refs("Explain section 2(24)(iia)") == [("2", ["24", "iia"])]


def test_bare_section_numbers_with_letters_are_recognised():
    assert refs("Can I claim both 80C and 80CCD(1B)?") == [("80C", []), ("80CCD", ["1B"])]
    assert refs("Is 80-IA still available?") == [("80-IA", [])]


def test_amounts_and_years_are_not_section_references():
    assert refs("I paid 150000 in 2025 as rent of 30 per cent") == []


def test_abbreviations_are_spelled_out_as_the_act_words_them():
    assert expand_abbreviations("Penalty for late TDS?") == "Penalty for late TDS (tax deducted at source)?"
    assert expand_abbreviations("is hra taxable") == "is hra (house rent allowance) taxable"


def test_abbreviations_that_are_english_words_need_capitals():
    assert expand_abbreviations("a pan or a mat") == "a pan or a mat"
    assert expand_abbreviations("PAN") == "PAN (permanent account number)"


def test_everyday_words_get_the_acts_terms():
    assert expand_abbreviations("Is a gift from my uncle taxable?") == \
        "Is a gift (received without consideration) from my uncle taxable?"
    assert expand_abbreviations("I rented out my flat") == "I rented out (let) my flat"
    assert expand_abbreviations("loss on crypto") == "loss on crypto (virtual digital asset)"
