from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

from taxqa.config import settings

MODEL = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384
# bge models are trained with this instruction on the query side only.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model() -> TextEmbedding:
    return TextEmbedding(MODEL, cache_dir=str(settings.model_cache_dir), threads=settings.embed_threads)


# Small batches keep the model's activation memory low; the server this runs on has 2 GB of RAM.
def embed_passages(texts: list[str], batch_size: int = 8) -> list[np.ndarray]:
    return list(_model().embed(texts, batch_size=batch_size))


def embed_query(text: str) -> np.ndarray:
    return next(iter(_model().embed([QUERY_PREFIX + text])))
