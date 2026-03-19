"""
Shared pytest fixtures and configuration.

Integration fixtures use an in-memory SQLite database.
JSONB and UUID are patched to SQLite-compatible types at import time.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.sqlite import insert as _sqlite_insert
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# ---------------------------------------------------------------------------
# SQLite compatibility: patch PG-specific types before any model import
# ---------------------------------------------------------------------------

# 1. JSONB → sa.JSON  (SQLite stores as TEXT, behaviour identical for tests)
postgresql.JSONB = sa.JSON  # type: ignore[assignment]

# 2. postgresql.insert → sqlite.insert  — SQLite's Insert also supports
#    on_conflict_do_update / on_conflict_do_nothing, so upsert code works.
postgresql.insert = _sqlite_insert  # type: ignore[assignment]

# 3. UUID(as_uuid=True) → String(36) TypeDecorator
#    - silently ignores the `as_uuid` kwarg
#    - coerces uuid.UUID objects → str on INSERT (SQLite stores as TEXT)
class _UUIDCompat(sa.TypeDecorator):
    impl = sa.String(36)
    cache_ok = True

    def __init__(self, *args, as_uuid: bool = True, **kwargs):  # noqa: ARG002
        super().__init__()

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        return value

postgresql.UUID = _UUIDCompat  # type: ignore[assignment]

# 4. BIGINT → INTEGER in SQLite DDL so that `autoincrement=True` on PK works.
#    SQLite only auto-generates rowids for `INTEGER PRIMARY KEY`, not `BIGINT`.
SQLiteTypeCompiler.visit_BIGINT = lambda self, type_, **kw: "INTEGER"  # type: ignore[method-assign]

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from infrastructure.database.models.base import Base
from infrastructure.database.repo.requests import RequestsRepo


# ---------------------------------------------------------------------------
# Integration DB fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """Creates a fresh in-memory SQLite engine for each test function."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_engine) -> AsyncSession:
    """Provides a session for the in-memory test DB."""
    session_factory = async_sessionmaker(
        bind=db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def repo(db_session: AsyncSession) -> RequestsRepo:
    """Provides a RequestsRepo backed by the in-memory test DB."""
    return RequestsRepo(session=db_session)


# ---------------------------------------------------------------------------
# Fixtures: standard question payloads (used by unit tests)
# ---------------------------------------------------------------------------

@pytest.fixture
def choice_answer() -> dict:
    return {"answer": "А", "options": 5}


@pytest.fixture
def short_answer() -> dict:
    return {"answer": "4.5"}


@pytest.fixture
def match_answer() -> dict:
    return {"pairs": {"1": "А", "2": "Б", "3": "В"}}
