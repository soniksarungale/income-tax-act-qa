from taxqa.answer import Answer, Citation, Claim
from taxqa.confidence import score
from taxqa.search import Hit


def hit(chunk_id, provision_id, similarity=0.0, sources=()):
    return Hit(chunk_id, f"Section {provision_id}", str(provision_id), "", 1, 1, "text", "", [], provision_id, [],
               similarity=similarity, sources=list(sources))


def claim(label, verified=True):
    return Claim("s", "q", [Citation(label, "ref", "", 1, 1)], verified, "" if verified else "quote not found")


def make(status="answered", claims=None, not_covered="", similarity=0.80, sources=("vector", "keyword")):
    retrieved = [hit(1, 10, similarity, sources)]
    return Answer("q", status, claims=claims if claims is not None else [claim("S1")], not_covered=not_covered,
                  sources=retrieved + [hit(2, 10)], retrieved=retrieved)


def test_strong_fully_verified_answer_is_high():
    c = score(make())
    assert c.score == 1.0 and c.label == "high"


def test_each_weakness_lowers_the_score():
    full = score(make()).score
    assert score(make(claims=[claim("S1"), claim("S2", verified=False)])).score < full
    assert score(make(similarity=0.70)).components["retrieval"] == 0.5
    assert score(make(sources=("vector",))).components["agreement"] == 0.0
    assert score(make(not_covered="the rate")).components["completeness"] == 0.5


def test_weak_answer_is_low():
    c = score(make(claims=[claim("S1"), claim("S2", False), claim("S2", False)], similarity=0.62,
                   sources=("vector",), not_covered="most of it"))
    assert c.label == "low"


def test_refusals_have_no_score():
    assert score(make(status="refused", claims=[])) is None
    assert score(make(status="error")) is None
