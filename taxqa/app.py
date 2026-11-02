"""Web app: uvicorn taxqa.app:app"""

import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from taxqa import llm
from taxqa.answer import Answer, answer, document
from taxqa.config import settings
from taxqa.confidence import score

log = logging.getLogger("taxqa")
STATIC = Path(__file__).parent / "static"
# Every question costs a model call on a shared plan or key; this keeps one visitor from using it up.
RATE_LIMIT, RATE_WINDOW = 10, 600

app = FastAPI(title="Income-tax Act QA", docs_url=None, redoc_url=None)
_requests: dict[str, deque] = defaultdict(deque)
_requests_lock = threading.Lock()


class Question(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


def _allow(client: str) -> bool:
    now = time.monotonic()
    with _requests_lock:
        times = _requests[client]
        while times and now - times[0] > RATE_WINDOW:
            times.popleft()
        if len(times) >= RATE_LIMIT:
            return False
        times.append(now)
        return True


def to_json(a: Answer) -> dict:
    confidence = score(a)
    cited = {c.label for claim in a.claims for c in claim.citations}
    return {
        "question": a.question,
        "status": a.status,
        "message": a.message,
        "document": a.document,
        "edition": a.edition,
        "claims": [
            {"statement": c.statement, "quote": c.quote, "verified": c.verified, "problem": c.problem,
             "citations": [{"label": x.label, "ref": x.ref, "heading": x.heading, "document": a.document,
                            "page_start": x.page_start, "page_end": x.page_end} for x in c.citations]}
            for c in a.claims
        ],
        "not_covered": a.not_covered,
        "confidence": confidence and {"score": confidence.score, "label": confidence.label,
                                      "components": confidence.components},
        # Only the extracts the answer relies on; the full list can run to dozens.
        "sources": [
            {"label": f"S{i}", "ref": h.ref, "heading": h.heading, "page_start": h.page_start,
             "page_end": h.page_end, "text": h.text, "amended_by": h.amended_by}
            for i, h in enumerate(a.sources, 1) if f"S{i}" in cited
        ],
        "extracts_considered": len(a.sources),
        "model": a.model,
        "timing_ms": {"retrieval": a.retrieval_ms, "llm": a.llm_ms},
    }


@app.post("/api/ask")
def ask(body: Question, request: Request) -> dict:
    if not _allow(request.client.host if request.client else "unknown"):
        raise HTTPException(429, "Too many questions from this address; please wait a few minutes.")
    result = answer(body.question)
    if result.status == "error":
        log.warning("answer failed: %s", result.message)
    return to_json(result)


@app.get("/api/info")
def info() -> dict:
    name, edition = document()
    try:
        model = llm.model_name()
    except llm.LLMError:
        model = ""
    return {"document": name, "edition": edition, "provider": settings.llm_provider, "model": model,
            "pdf_available": settings.act_pdf_path.exists()}


@app.get("/act.pdf")
def act_pdf() -> FileResponse:
    # Served so that citations can open the official PDF at the cited page (act.pdf#page=92).
    if not settings.act_pdf_path.exists():
        raise HTTPException(404, "The Act PDF is not on this server.")
    return FileResponse(settings.act_pdf_path, media_type="application/pdf",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
