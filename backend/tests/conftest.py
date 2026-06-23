"""
Shared pytest fixtures — expanded each phase.

Phase 1: No fixtures required (infrastructure tests use direct connections).
Phase 2: db_session — connects to wa_test, creates tables, truncates after each test.
Phase 4: client (httpx AsyncClient against the FastAPI app), mock_claude.
Phase 5: client overrides get_db with db_session; sample_contact.

Multi-tenancy & auth: a `default_org` (org + owner user + membership) is created
for endpoint tests, and `client` is authenticated as that owner by default.
Direct-model inserts in tests must pass `organization_id=default_org.id`.
"""
import os
import uuid

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

# Stable identifiers for the default test organization / owner.
DEFAULT_ORG_PNID = "test_pnid_default"


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
async def default_org(db_session: AsyncSession):
    """A ready-to-use organization with an owner user + membership.

    Has a WhatsApp phone_number_id set so webhook-routing tests can target it.
    Returns the Organization instance.
    """
    from app.models.organization import Organization
    from app.models.user import Membership, Role, User
    from app.security import hash_password

    org = Organization(
        name="Test Org",
        slug=f"test-org-{uuid.uuid4().hex[:6]}",
        whatsapp_phone_number_id=DEFAULT_ORG_PNID,
    )
    owner = User(email="owner@test.com", password_hash=hash_password("password123"))
    db_session.add_all([org, owner])
    await db_session.flush()
    db_session.add(
        Membership(user_id=owner.id, organization_id=org.id, role=Role.owner)
    )
    await db_session.commit()
    # Stash the owner id for token-minting helpers.
    org._owner_id = owner.id  # type: ignore[attr-defined]
    return org


def _access_token_for(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    from app.security import create_access_token

    return create_access_token(user_id=user_id, organization_id=org_id, role=role)


@pytest.fixture
def auth_headers(default_org):
    """Authorization header for the default org's owner."""
    token = _access_token_for(default_org._owner_id, default_org.id, "owner")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_token():
    """Factory to mint an access token for arbitrary (user_id, org_id, role)."""

    def _make(user_id: uuid.UUID, org_id: uuid.UUID, role: str = "owner") -> str:
        return _access_token_for(user_id, org_id, role)

    return _make


@pytest.fixture
async def client(db_session: AsyncSession, default_org):
    """
    httpx AsyncClient wired to the FastAPI app via ASGI transport.

    Overrides get_db so endpoint DB operations share the test's db_session, and
    sends the default org owner's bearer token on every request so existing
    endpoint suites remain authenticated. Tests can override the Authorization
    header per-request to act as a different principal.
    """
    from app.database import get_db
    from app.main import app  # imported here so pytest-env vars are already set

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    token = _access_token_for(default_org._owner_id, default_org.id, "owner")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
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
async def sample_contact(db_session: AsyncSession, default_org):
    """Pre-inserted opted-in contact (+919876543210, tag=purchased) in the default org."""
    from app.models.contact import Contact

    contact = Contact(
        organization_id=default_org.id,
        name="Priya Sharma",
        phone="+919876543210",
        opted_in=True,
        tags=["purchased"],
    )
    db_session.add(contact)
    await db_session.commit()
    return contact
