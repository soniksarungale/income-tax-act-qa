from contextlib import contextmanager
from pathlib import Path

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from taxqa.config import settings

SCHEMA = Path(__file__).with_name("schema.sql")

_pool: ConnectionPool | None = None


def _configure(conn: psycopg.Connection) -> None:
    register_vector(conn)


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            configure=_configure,
            open=True,
        )
    return _pool


@contextmanager
def connection():
    with pool().connection() as conn:
        yield conn


def init_schema() -> None:
    # The vector type must exist before register_vector runs, so use a plain connection here.
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(SCHEMA.read_text())
