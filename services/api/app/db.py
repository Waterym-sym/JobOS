"""Async PostgreSQL connection pool (psycopg3).

The pool is a module-level singleton: the api (8000) and ws-gateway (8788)
uvicorn servers run in the same process and share it.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from services.api.app.config import get_settings

_pool: AsyncConnectionPool | None = None


def _conninfo() -> str:
    url = get_settings().database_url
    # SQLAlchemy-style scheme ("postgresql+psycopg://") is rejected by libpq;
    # accept it anyway and normalize to "postgresql://".
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


async def init_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            _conninfo(),
            min_size=1,
            max_size=8,
            open=False,
            kwargs={"autocommit": False},
        )
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    pool = await init_pool()
    async with pool.connection() as conn:
        yield conn
