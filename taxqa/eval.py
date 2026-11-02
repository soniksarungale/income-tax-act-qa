"""Run the evaluation set through the full pipeline: python -m taxqa.eval [--out eval/results.md]

For each question in eval/questions.json:
- answerable questions list the sections a correct answer must rely on ("sections", at least one)
  and others it may usefully cite ("also");
- out-of-scope questions are marked "refuse": true.

Reported per question and in total:
- retrieved: one of the required sections was among the extracts given to the model;
- cited: a verified claim cites one of the required sections;
- refusal: the answer was refused exactly when it should have been;
- verified: share of claims whose citations checked out.
Every question makes one LLM call, so a full run takes a few minutes with claude-cli.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from taxqa.answer import answer
from taxqa.confidence import score

QUESTIONS = Path(__file__).parent.parent / "eval" / "questions.json"


def run(questions: list[dict]) -> list[dict]:
    rows = []
    for i, q in enumerate(questions, 1):
        a = answer(q["question"])
        extracts = {h.number for h in a.sources}
        by_label = {f"S{n}": h for n, h in enumerate(a.sources, 1)}
        cited = {by_label[c.label].number for claim in a.claims if claim.verified for c in claim.citations}
        required = set(q.get("sections", []))
        confidence = score(a)
        row = {
            "question": q["question"],
            "refuse": bool(q.get("refuse")),
            "status": a.status,
            "retrieved": bool(required & extracts) if required else None,
            "cited": bool(required & cited) if required else None,
            "refusal_ok": (a.status == "refused") == bool(q.get("refuse")),
            "claims": len(a.claims),
            "verified": sum(c.verified for c in a.claims),
            "cited_sections": sorted(cited),
            "confidence": confidence.score if confidence else None,
            "seconds": round((a.retrieval_ms + a.llm_ms) / 1000, 1),
            "message": a.message,
            "unverified": [{"statement": c.statement, "quote": c.quote, "problem": c.problem,
                            "cited": [x.ref for x in c.citations]} for c in a.claims if not c.verified],
        }
        rows.append(row)
        print(f"[{i}/{len(questions)}] {row['status']:8} refusal_ok={row['refusal_ok']} cited={row['cited']} "
              f"{row['verified']}/{row['claims']} verified  {q['question'][:60]}", flush=True)
    return rows


def summary(rows: list[dict]) -> dict:
    answerable = [r for r in rows if not r["refuse"]]
    claims = sum(r["claims"] for r in rows)
    return {
        "questions": len(rows),
        "retrieval_hit": f"{sum(r['retrieved'] for r in answerable)}/{len(answerable)}",
        "citation_hit": f"{sum(r['cited'] for r in answerable)}/{len(answerable)}",
        "refusal_correct": f"{sum(r['refusal_ok'] for r in rows)}/{len(rows)}",
        "claims_verified": f"{sum(r['verified'] for r in rows)}/{claims}",
        "errors": sum(r["status"] == "error" for r in rows),
    }


def report(rows: list[dict], totals: dict) -> str:
    def mark(value):
        return "-" if value is None else "yes" if value else "**no**"

    lines = ["# Evaluation results", "", "| Measure | Result |", "|---|---|"]
    lines += [f"| {k.replace('_', ' ')} | {v} |" for k, v in totals.items()]
    lines += ["", "| # | Question | Status | Retrieved | Cited | Refusal correct | Verified claims | Confidence | Sections cited | Time (s) |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        question = r["question"] if len(r["question"]) <= 90 else r["question"][:87] + "..."
        conf = "-" if r["confidence"] is None else f"{r['confidence']:.2f}"
        lines.append(f"| {i} | {question} | {r['status']} | {mark(r['retrieved'])} | {mark(r['cited'])} | "
                     f"{mark(r['refusal_ok'])} | {r['verified']}/{r['claims']} | {conf} | "
                     f"{', '.join(r['cited_sections']) or '-'} | {r['seconds']} |")
    flagged = [(i, u) for i, r in enumerate(rows, 1) for u in r["unverified"]]
    if flagged:
        lines += ["", "## Claims that failed verification", "",
                  "Shown to the user marked \"Not verified\", with the reason.", ""]
        for i, u in flagged:
            lines.append(f"- Question {i}: {u['problem']}. Cited {', '.join(u['cited']) or 'nothing'}. "
                         f"Statement: {u['statement']} Quote given: \"{u['quote']}\"")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--questions", type=Path, default=QUESTIONS)
    parser.add_argument("--out", type=Path, help="write a Markdown report here")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    rows = run(json.loads(args.questions.read_text()))
    totals = summary(rows)
    print(json.dumps(totals, indent=2))
    if args.out:
        args.out.write_text(report(rows, totals))


if __name__ == "__main__":
    main()
