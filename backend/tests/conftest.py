"""
Shared pytest fixtures — expanded each phase.

Phase 1: No fixtures required (infrastructure tests use direct connections).
Phase 2: db_session — connects to wa_test, creates tables, truncates after each test.
Phase 3+: client, mock_wa, mock_claude added here.
"""
import os

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
import app.models  # noqa: F401 — registers all models with Base.metadata

TEST_DB_URL = os.getenv(
    "TEST_DB_URL",
    "postgresql+asyncpg://wa:wa@postgres:5432/wa_test",
)


@pytest.fixture
async def db_session() -> AsyncSession:
    """
    Async DB session backed by wa_test.

    On first call: creates all tables (checkfirst=True, so no-op if already exist).
    After each test: rolls back uncommitted changes, then truncates all tables so
    the next test starts from a clean slate.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    async with factory() as session:
        yield session
        await session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(
                sa.text(f'TRUNCATE TABLE "{table.name}" CASCADE')
            )
        await session.commit()

    await engine.dispose()
