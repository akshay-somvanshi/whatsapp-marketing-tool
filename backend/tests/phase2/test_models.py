"""Phase 2 — SQLAlchemy model and Alembic migration tests."""
import os
import subprocess
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus

async def test_create_and_read_contact(db_session):
    contact = Contact(name="Priya Sharma", phone="+919876543210", opted_in=True)
    db_session.add(contact)
    await db_session.flush()

    result = await db_session.get(Contact, contact.id)
    assert result.name == "Priya Sharma"
    assert result.phone == "+919876543210"
    assert result.opted_in is True
    assert result.tags == []
    assert result.created_at is not None


async def test_contact_phone_unique_constraint(db_session):
    c1 = Contact(name="Priya", phone="+919876543210")
    db_session.add(c1)
    await db_session.flush()

    c2 = Contact(name="Rahul", phone="+919876543210")
    db_session.add(c2)
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_message_fk_and_fields(db_session):
    contact = Contact(name="Test User", phone="+919000000001")
    db_session.add(contact)
    await db_session.flush()

    msg = Message(
        contact_phone=contact.phone,
        direction=MessageDirection.inbound,
        body="Hello there",
        status=MessageStatus.sent,
    )
    db_session.add(msg)
    await db_session.flush()

    result = await db_session.get(Message, msg.id)
    assert result.body == "Hello there"
    assert result.direction == MessageDirection.inbound
    assert result.status == MessageStatus.sent
    assert result.template_name is None
    assert result.created_at is not None


async def test_conversation_fk_and_defaults(db_session):
    contact = Contact(name="Conv User", phone="+919000000002")
    db_session.add(contact)
    await db_session.flush()

    conv = Conversation(
        contact_phone=contact.phone,
        session_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db_session.add(conv)
    await db_session.flush()

    result = await db_session.get(Conversation, conv.id)
    assert result.ai_enabled is True
    assert result.status == ConversationStatus.active


async def test_conversation_unique_per_contact(db_session):
    contact = Contact(name="Only One Conv", phone="+919000000003")
    db_session.add(contact)
    await db_session.flush()

    exp = datetime.now(timezone.utc) + timedelta(hours=24)
    db_session.add(Conversation(contact_phone=contact.phone, session_expires_at=exp))
    await db_session.flush()

    db_session.add(Conversation(contact_phone=contact.phone, session_expires_at=exp))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_campaign_default_counts_and_status(db_session):
    campaign = Campaign(
        name="Summer Sale",
        template_name="review_request",
        audience_tags=["purchased"],
    )
    db_session.add(campaign)
    await db_session.flush()

    result = await db_session.get(Campaign, campaign.id)
    assert result.sent_count == 0
    assert result.delivered_count == 0
    assert result.read_count == 0
    assert result.status == CampaignStatus.draft
    assert result.template_params == {}
    assert result.scheduled_at is None


def test_alembic_migration_at_head():
    """Verifies the wa_marketing DB has the latest migration applied."""
    # Override DATABASE_URL so the subprocess checks wa_marketing, not wa_test
    # (pytest.ini sets DATABASE_URL=wa_test for all test-scope processes).
    env = {
        **os.environ,
        "DATABASE_URL": "postgresql+asyncpg://wa:wa@postgres:5432/wa_marketing",
    }
    result = subprocess.run(
        ["alembic", "current"],
        capture_output=True,
        text=True,
        cwd="/app",
        env=env,
    )
    assert result.returncode == 0, f"alembic current failed:\n{result.stderr}"
    assert "(head)" in result.stdout, (
        f"Migration not at head. alembic current output:\n{result.stdout}"
    )
