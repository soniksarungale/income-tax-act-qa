import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from taxqa.db import connection
from taxqa.embed import embed_query

RRF_K = 60  # standard reciprocal-rank-fusion constant
CANDIDATES = 40
# Terms in more than this share of chunks ("section", "shall", "income", "tax") say nothing about
# which provision a question is about.
MAX_TERM_SHARE = 0.2
# A long question about one topic otherwise fills every slot with one section (80EE for a home-loan
# question) and pushes out the sections that actually answer it (23 and 24).
PER_SECTION = 3
# Provisos and Explanations change the rule they follow, so the answer step sees more than the hits:
# short provisions whole, longer ones as the hits plus the text they hang from.
WHOLE_PROVISION_CHARS = 6000  # about 90% of provisions
CONTEXT_BUDGET_CHARS = 24000

# "section 24(b)", "sec. 80C", "s. 139(1)", "u/s 54F", "80-IA". Bare numbers are ignored; they are
# usually amounts or years.
SECTION_REF = re.compile(
    r"\b(?:sections?|sec\.?|s\.|u/s\.?)\s*(\d{1,3}[A-Z]{0,4}(?:-[A-Z]{1,3})?)((?:\s*\([0-9A-Za-z]{1,6}\))*)",
    re.I,
)
STANDALONE_REF = re.compile(r"\b(\d{1,3}(?:[A-Z]{1,4}|-[A-Z]{1,3}))((?:\([0-9A-Za-z]{1,6}\))*)")

# People ask in practitioners' shorthand; the Act spells these out, so neither search finds them.
ABBREVIATIONS = {
    "TDS": "tax deducted at source", "TCS": "tax collected at source", "HRA": "house rent allowance",
    "LTCG": "long-term capital gains", "STCG": "short-term capital gains", "HUF": "Hindu undivided family",
    "NRI": "non-resident Indian", "ITR": "return of income", "CBDT": "Central Board of Direct Taxes",
    "STT": "securities transaction tax", "LLP": "limited liability partnership", "NPS": "National Pension System",
    "PF": "provident fund", "EPF": "provident fund", "PAN": "permanent account number",
    "AO": "Assessing Officer", "AY": "assessment year", "FY": "previous year", "MAT": "book profit",
}
# Matched only in capitals where the lower-case form is an English word ("pan", "mat", "ay").
_ABBREVIATION = re.compile(r"\b(" + "|".join(ABBREVIATIONS) + r")\b")
_ABBREVIATION_ANY_CASE = re.compile(r"\b(tds|tcs|hra|ltcg|stcg|huf|nri|itr|cbdt|stt|nps|epf)\b", re.I)


@dataclass
class SectionRef:
    number: str
    path: list[str]


@dataclass
class Hit:
    chunk_id: int
    ref: str
    number: str
    heading: str
    page_start: int
    page_end: int
    text: str
    context: str
    amended_by: list[str]
    provision_id: int
    path: list[str]
    similarity: float = 0.0  # cosine similarity to the question
    keyword_rank: float = 0.0
    score: float = 0.0
    sources: list[str] = field(default_factory=list)


def expand_abbreviations(question: str) -> str:
    def add(m: re.Match) -> str:
        return f"{m.group(0)} ({ABBREVIATIONS[m.group(0).upper()]})"
    question = _ABBREVIATION.sub(add, question)
    return _ABBREVIATION_ANY_CASE.sub(lambda m: m.group(0) if m.group(0).isupper() else add(m), question)


def section_refs(question: str) -> list[SectionRef]:
    refs: list[SectionRef] = []
    for pattern in (SECTION_REF, STANDALONE_REF):
        for m in pattern.finditer(question):
            number = m.group(1).upper()
            path = re.findall(r"\(([0-9A-Za-z]+)\)", m.group(2) or "")
            if not any(r.number == number and r.path == path for r in refs):
                refs.append(SectionRef(number, path))
    return refs


@lru_cache(maxsize=1)
def _term_weights() -> dict[str, float]:
    # Postgres full-text ranking has no inverse document frequency, so a common word like "paid"
    # counts as much as "tuition". Weights are computed once from the index.
    with connection() as conn:
        total = conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]
        rows = conn.execute("SELECT word, ndoc FROM ts_stat('SELECT tsv FROM chunks')").fetchall()
    return {r["word"]: math.log(total / r["ndoc"]) for r in rows if r["ndoc"] <= total * MAX_TERM_SHARE}


def keyword_terms(conn, question: str) -> list[tuple[str, float]]:
    """The question's stemmed terms that occur in the index, with their weights."""
    lexemes = conn.execute(
        "SELECT unnest(tsvector_to_array(to_tsvector('english', %s))) AS word", (question,)
    ).fetchall()
    weights = _term_weights()
    return [(r["word"], weights[r["word"]]) for r in lexemes if r["word"] in weights]


def _tsquery_literal(word: str) -> str:
    return "'" + word.replace("\\", "\\\\").replace("'", "''") + "'"


_SELECT = """
    SELECT c.id, c.ref, p.number, p.heading, c.page_start, c.page_end, c.text, c.context, c.amended_by,
           c.provision_id, c.path
    FROM chunks c JOIN provisions p ON p.id = c.provision_id
"""


def _hit(row: dict) -> Hit:
    return Hit(row["id"], row["ref"], row["number"], row["heading"], row["page_start"], row["page_end"],
               row["text"], row["context"], row["amended_by"], row["provision_id"], row["path"])


def search(question: str, limit: int = 12) -> list[Hit]:
    named = section_refs(question)
    question = expand_abbreviations(question)
    vector = embed_query(question)
    hits: dict[int, Hit] = {}
    rankings: dict[str, list[int]] = {}

    with connection() as conn:
        rows = conn.execute(
            _SELECT.replace("SELECT", "SELECT 1 - (c.embedding <=> %s) AS similarity,", 1)
            + " ORDER BY c.embedding <=> %s LIMIT %s",
            (vector, vector, CANDIDATES),
        ).fetchall()
        rankings["vector"] = []
        for row in rows:
            h = hits.setdefault(row["id"], _hit(row))
            h.similarity = float(row["similarity"])
            rankings["vector"].append(row["id"])

        rankings["keyword"] = []
        terms = keyword_terms(conn, question)
        if terms:
            # Sum of the weights of the question terms a chunk contains (binary BM25 without length
            # normalisation; chunks are capped at 1800 characters anyway).
            score = " + ".join("%s * (c.tsv @@ %s::tsquery)::int" for _ in terms)
            params = [x for word, weight in terms for x in (weight, _tsquery_literal(word))]
            any_term = " | ".join(_tsquery_literal(word) for word, _ in terms)
            rows = conn.execute(
                _SELECT.replace("SELECT", f"SELECT {score} AS rank,", 1)
                # Many chunks tie on the same terms; the closer meaning decides among them.
                + " WHERE c.tsv @@ %s::tsquery ORDER BY rank DESC, c.embedding <=> %s LIMIT %s",
                (*params, any_term, vector, CANDIDATES),
            ).fetchall()
            for row in rows:
                h = hits.setdefault(row["id"], _hit(row))
                h.keyword_rank = float(row["rank"])
                rankings["keyword"].append(row["id"])

        rankings["section"] = []
        for ref in named:
            rows = conn.execute(
                _SELECT + " WHERE p.number = %s AND c.path[1:%s] = %s ORDER BY c.id LIMIT %s",
                (ref.number, len(ref.path), ref.path, 12),
            ).fetchall()
            for row in rows:
                hits.setdefault(row["id"], _hit(row))
                rankings["section"].append(row["id"])

        missing = [h.chunk_id for h in hits.values() if h.similarity == 0.0]
        if missing:
            for row in conn.execute(
                "SELECT id, 1 - (embedding <=> %s) AS similarity FROM chunks WHERE id = ANY(%s)", (vector, missing)
            ):
                hits[row["id"]].similarity = float(row["similarity"])

    for source, ids in rankings.items():
        for rank, chunk_id in enumerate(ids):
            hits[chunk_id].score += 1 / (RRF_K + rank + 1)
            hits[chunk_id].sources.append(source)

    # Sections named in the question are exempt from the cap.
    exempt = {r.number for r in named}
    taken: dict[str, int] = {}
    results = []
    for h in sorted(hits.values(), key=lambda h: h.score, reverse=True):
        if h.number not in exempt and taken.get(h.number, 0) >= PER_SECTION:
            continue
        taken[h.number] = taken.get(h.number, 0) + 1
        results.append(h)
        if len(results) == limit:
            break
    return results


def expand(hits: list[Hit], named: set[str] = frozenset()) -> list[Hit]:
    """The text to answer from. For each provision hit, in rank order: the whole provision if it is
    short or named in the question; otherwise the hits, every chunk above them (the section opening,
    the sub-section a clause belongs to, the clause a proviso qualifies) and the sub-sections that
    text refers to. Within a provision, chunks keep the Act's order. Chunks added here have no
    retrieval score."""
    order = list(dict.fromkeys(h.provision_id for h in hits))
    if not order:
        return []
    with connection() as conn:
        rows = conn.execute(_SELECT + " WHERE c.provision_id = ANY(%s) ORDER BY c.id", (order,)).fetchall()
    by_id = {h.chunk_id: h for h in hits}
    chunks: dict[int, list[dict]] = {}
    for row in rows:
        chunks.setdefault(row["provision_id"], []).append(row)

    extracts: list[Hit] = []
    used = 0
    for provision_id in order:
        rows = chunks[provision_id]
        size = sum(len(r["text"]) for r in rows)
        whole = size <= WHOLE_PROVISION_CHARS or (rows[0]["number"] in named and used + size <= CONTEXT_BUDGET_CHARS)
        if not whole:
            rows = _around_hits(rows, [h for h in hits if h.provision_id == provision_id])
            size = sum(len(r["text"]) for r in rows)
        if extracts and used + size > CONTEXT_BUDGET_CHARS:
            continue
        used += size
        extracts.extend(by_id.get(r["id"]) or _hit(r) for r in rows)
    return extracts


# "sub-section (4)" on its own means this section's; "sub-section (1) of section 80CCD" does not.
INTERNAL_REF = re.compile(r"\bsub-sections? \((\w{1,5})\)(?!\s*(?:of|to) (?:section|the)\b)")
CROSS_REF_CHARS = 2500


def _around_hits(rows: list[dict], hits: list[Hit]) -> list[dict]:
    def is_ancestor(path: list[str]) -> bool:
        return any(len(path) < len(h.path) and h.path[:len(path)] == path for h in hits)

    hit_ids = {h.chunk_id for h in hits}
    keep = {r["id"] for r in rows if r["id"] in hit_ids or is_ancestor(r["path"])}
    text = " ".join(r["text"] for r in rows if r["id"] in keep)
    for label in dict.fromkeys(INTERNAL_REF.findall(text)):
        part = [r for r in rows if r["path"][:1] == [label]]
        if part and sum(len(r["text"]) for r in part) <= CROSS_REF_CHARS:
            keep.update(r["id"] for r in part)
    return [r for r in rows if r["id"] in keep]
