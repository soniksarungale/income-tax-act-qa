"""Load the Act PDF into Postgres: python -m taxqa.ingest [--pdf PATH] [--force]

Text is stored first and embeddings are filled in afterwards in small batches, so the run needs
little memory and can be resumed: rerunning only embeds chunks that do not have a vector yet.
"""

import argparse
import hashlib
import logging
import sys
import time
from pathlib import Path

from taxqa.config import settings
from taxqa.db import connection, init_schema
from taxqa.embed import embed_passages
from taxqa.parser import Chunk, parse_pdf

log = logging.getLogger("taxqa.ingest")

DOCUMENT_NAME = "Income-tax Act, 1961"
EMBED_BATCH = 64


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def embedding_text(ref: str, context: str, text: str) -> str:
    return f"{ref}. {context}\n{text}"


def _chunk_row(provision_id: int, c: Chunk) -> tuple:
    return (provision_id, c.ref, list(c.path), c.page_start, c.page_end, c.text, c.context, c.amended_by)


def store_text(pdf: Path, digest: str) -> None:
    started = time.monotonic()
    act = parse_pdf(pdf)
    if not act.edition:
        raise SystemExit("Could not find the 'AS AMENDED BY' edition line; is this the official PDF?")
    log.info("Parsed %d provisions, %d chunks in %.0fs", len(act.provisions),
             sum(len(p.chunks) for p in act.provisions), time.monotonic() - started)

    with connection() as conn, conn.transaction():
        # One edition of the Act at a time: replacing it keeps citations unambiguous.
        conn.execute("DELETE FROM documents")
        doc_id = conn.execute(
            "INSERT INTO documents (name, edition, sha256, page_count) VALUES (%s, %s, %s, %s) RETURNING id",
            (DOCUMENT_NAME, f"As amended by {act.edition}", digest, act.page_count),
        ).fetchone()["id"]
        for p in act.provisions:
            provision_id = conn.execute(
                """INSERT INTO provisions (document_id, kind, number, heading, chapter, chapter_title,
                                           page_start, page_end, text, omitted, seq)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (doc_id, p.kind, p.number, p.heading, p.chapter, p.chapter_title,
                 p.page_start, p.page_end, p.text, p.omitted, p.seq),
            ).fetchone()["id"]
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO chunks (provision_id, ref, path, page_start, page_end, text, context, amended_by)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    [_chunk_row(provision_id, c) for c in p.chunks],
                )
    log.info("Stored %s (%s), %d pages", DOCUMENT_NAME, act.edition, act.page_count)


def fill_embeddings() -> None:
    with connection() as conn:
        total = conn.execute("SELECT count(*) AS n FROM chunks WHERE embedding IS NULL").fetchone()["n"]
    if not total:
        log.info("All chunks already have embeddings")
        return
    log.info("Embedding %d chunks", total)
    started, done = time.monotonic(), 0
    while True:
        with connection() as conn, conn.transaction():
            rows = conn.execute(
                "SELECT id, ref, context, text FROM chunks WHERE embedding IS NULL ORDER BY id LIMIT %s",
                (EMBED_BATCH,),
            ).fetchall()
            if not rows:
                break
            vectors = embed_passages([embedding_text(r["ref"], r["context"], r["text"]) for r in rows])
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE chunks SET embedding = %s WHERE id = %s",
                    [(v, r["id"]) for v, r in zip(vectors, rows)],
                )
        done += len(rows)
        if done % 1024 < EMBED_BATCH:
            log.info("  %d / %d (%.0fs)", done, total, time.monotonic() - started)
    log.info("Embedded %d chunks in %.0fs", done, time.monotonic() - started)


def ingest(pdf: Path, force: bool = False) -> None:
    if not pdf.exists():
        raise SystemExit(f"PDF not found: {pdf}. See README for where to download it.")
    init_schema()
    digest = sha256(pdf)
    with connection() as conn:
        existing = conn.execute("SELECT id FROM documents WHERE sha256 = %s", (digest,)).fetchone()
    if force or not existing:
        store_text(pdf, digest)
    else:
        log.info("Text already stored for this PDF; resuming embeddings (use --force to rebuild)")
    fill_embeddings()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=settings.act_pdf_path)
    parser.add_argument("--force", action="store_true", help="re-parse and re-index even if this PDF is loaded")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ingest(args.pdf, args.force)


if __name__ == "__main__":
    main()
