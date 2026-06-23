"""Phase 5 — Conversations API tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from app.models.contact import Contact
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus


PHONE = "+919876543210"
ENCODED_PHONE = quote(PHONE, safe="")  # %2B919876543210


async def _seed_contact_and_conv(db_session, default_org, *, ai_enabled: bool = True) -> tuple:
    contact = Contact(organization_id=default_org.id, phone=PHONE, name="Test User", opted_in=True)
    db_session.add(contact)
    await db_session.flush()

    conv = Conversation(
        organization_id=default_org.id,
        contact_phone=PHONE,
        session_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        status=ConversationStatus.active,
        ai_enabled=ai_enabled,
    )
    db_session.add(conv)
    await db_session.commit()
    return contact, conv


# ---------------------------------------------------------------------------
# GET /conversations
# ---------------------------------------------------------------------------


async def test_list_conversations_includes_session_status(client, db_session, default_org):
    await _seed_contact_and_conv(db_session, default_org)

    resp = await client.get("/conversations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert "session_status" in data[0]
    assert data[0]["session_status"] == "active"
    assert data[0]["contact_phone"] == PHONE


# ---------------------------------------------------------------------------
# GET /conversations/{phone}
# ---------------------------------------------------------------------------


async def test_get_conversation_returns_ordered_message_history(client, db_session, default_org):
    contact, _ = await _seed_contact_and_conv(db_session, default_org)

    # Add two messages in sequence
    db_session.add_all([
        Message(
            organization_id=default_org.id,
            contact_phone=PHONE,
            direction=MessageDirection.inbound,
            body="Hello",
            status=MessageStatus.sent,
        ),
        Message(
            organization_id=default_org.id,
            contact_phone=PHONE,
            direction=MessageDirection.outbound,
            body="Hi there!",
            status=MessageStatus.sent,
        ),
    ])
    await db_session.commit()

    resp = await client.get(f"/conversations/{ENCODED_PHONE}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["contact_phone"] == PHONE
    assert "session_status" in data

    messages = data["messages"]
    assert len(messages) == 2
    assert messages[0]["body"] == "Hello"
    assert messages[0]["direction"] == "inbound"
    assert messages[1]["body"] == "Hi there!"
    assert messages[1]["direction"] == "outbound"


# ---------------------------------------------------------------------------
# PATCH /conversations/{phone}
# ---------------------------------------------------------------------------


async def test_patch_conversation_toggles_ai_enabled(client, db_session, default_org):
    _, conv = await _seed_contact_and_conv(db_session, default_org, ai_enabled=True)

    resp = await client.patch(f"/conversations/{ENCODED_PHONE}", json={"ai_enabled": False})
    assert resp.status_code == 200
    assert resp.json()["ai_enabled"] is False

    # Flip back
    resp = await client.patch(f"/conversations/{ENCODED_PHONE}", json={"ai_enabled": True})
    assert resp.status_code == 200
    assert resp.json()["ai_enabled"] is True
