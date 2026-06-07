"""
Shared pytest fixtures — expanded each phase.

Phase 1: No fixtures required (infrastructure tests use direct connections).
Phase 2: db_session — connects to wa_test, creates tables, truncates after each test.
Phase 4: client (httpx AsyncClient against the FastAPI app), mock_claude.
Phase 5: client overrides get_db with db_session; sample_contact.
"""
import os

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
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
    Before and after each test: truncates all tables for a clean slate.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, checkfirst=True)

    async with factory() as session:
        # Pre-test cleanup: guard against dirty state from a crashed previous run
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(sa.text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
        await session.commit()

        yield session

        # Post-test cleanup
        await session.rollback()
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(sa.text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
        await session.commit()

    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession):
    """
    httpx AsyncClient wired to the FastAPI app via ASGI transport.

    Overrides the get_db dependency so all endpoint DB operations share
    the test's db_session — data written by endpoints is immediately
    visible to test assertions without separate commit.
    """
    from app.database import get_db
    from app.main import app  # imported here so pytest-env vars are already set

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_claude(monkeypatch):
    """
    Replaces app.tasks.celery_app.generate_reply with a deterministic stub.

    Returns the canned response {"action": "reply", "text": "Auto-reply from AI"}
    so tests can assert on the saved outbound message body.
    """
    async def _canned(*args, **kwargs):
        return {"action": "reply", "text": "Auto-reply from AI"}

    monkeypatch.setattr("app.tasks.celery_app.generate_reply", _canned)
    return _canned


@pytest.fixture
async def sample_contact(db_session: AsyncSession):
    """Pre-inserted opted-in contact (+919876543210, tag=purchased) for tests that need one."""
    from app.models.contact import Contact

    contact = Contact(
        name="Priya Sharma",
        phone="+919876543210",
        opted_in=True,
        tags=["purchased"],
    )
    db_session.add(contact)
    await db_session.commit()
    return contact
