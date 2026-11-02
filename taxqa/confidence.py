"""A confidence score for an answer, computed from evidence rather than asked of the model.

Models are poor judges of their own accuracy, so the score combines four things the server can
measure (weights in WEIGHTS):

- verified: share of the answer's claims whose citations and quotes checked out.
- retrieval: how closely the cited provisions matched the question. The best cosine similarity of
  a retrieved chunk in each cited provision, scaled from SIMILARITY_FLOOR (0) to SIMILARITY_CEILING
  (1), averaged. On this index, questions the Act answers score about 0.66-0.80 at the top and
  unrelated ones 0.50-0.67, which sets the range.
- agreement: share of cited provisions found by at least two of the three searches (meaning,
  keywords, section named in the question).
- completeness: 1 if the model reported nothing left unanswered, else 0.5.

Similarity alone cannot tell answerable questions from unanswerable ones (the ranges overlap), so
refusing is decided by citation verification, not by this score. Refusals and errors get no score.
"""

from dataclasses import dataclass, field

WEIGHTS = {"verified": 0.40, "retrieval": 0.30, "agreement": 0.15, "completeness": 0.15}
SIMILARITY_FLOOR = 0.60
SIMILARITY_CEILING = 0.80
HIGH, MEDIUM = 0.75, 0.50


@dataclass
class Confidence:
    score: float
    label: str  # "high", "medium" or "low"
    components: dict[str, float] = field(default_factory=dict)


def _scaled(similarity: float) -> float:
    return min(1.0, max(0.0, (similarity - SIMILARITY_FLOOR) / (SIMILARITY_CEILING - SIMILARITY_FLOOR)))


def score(answer) -> Confidence | None:
    if answer.status not in ("answered", "partial") or not answer.claims:
        return None
    verified = [c for c in answer.claims if c.verified]
    by_label = {f"S{i}": h for i, h in enumerate(answer.sources, 1)}
    cited = {by_label[c.label].provision_id for claim in verified for c in claim.citations if c.label in by_label}

    best: dict[int, float] = {}
    methods: dict[int, set[str]] = {}
    for h in answer.retrieved:
        best[h.provision_id] = max(best.get(h.provision_id, 0.0), h.similarity)
        methods.setdefault(h.provision_id, set()).update(h.sources)

    components = {
        "verified": len(verified) / len(answer.claims),
        "retrieval": sum(_scaled(best.get(p, 0.0)) for p in cited) / len(cited) if cited else 0.0,
        "agreement": sum(len(methods.get(p, ())) >= 2 for p in cited) / len(cited) if cited else 0.0,
        "completeness": 0.5 if answer.not_covered else 1.0,
    }
    total = round(sum(WEIGHTS[k] * v for k, v in components.items()), 2)
    label = "high" if total >= HIGH else "medium" if total >= MEDIUM else "low"
    return Confidence(total, label, {k: round(v, 2) for k, v in components.items()})
