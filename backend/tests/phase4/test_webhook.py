"""Phase 4 — Webhook endpoint and inbound message processing tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import sqlalchemy as sa

from app.models.contact import Contact
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection, MessageStatus
from app.tasks.celery_app import _process_inbound_message_async
from tests.conftest import DEFAULT_ORG_PNID


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------


def _inbound_payload(
    phone: str = "919876543210",
    body: str = "Hello",
    wa_msg_id: str = "wamid.test001",
    phone_number_id: str = DEFAULT_ORG_PNID,
) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "messages": [
                                {
                                    "from": phone,
                                    "id": wa_msg_id,
                                    "timestamp": "1700000000",
                                    "text": {"body": body},
                                    "type": "text",
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


def _status_payload(
    wa_msg_id: str, status: str, phone_number_id: str = DEFAULT_ORG_PNID
) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": phone_number_id},
                            "statuses": [
                                {
                                    "id": wa_msg_id,
                                    "status": status,
                                    "timestamp": "1700000001",
                                }
                            ],
                        }
                    }
                ]
            }
        ],
    }


# ---------------------------------------------------------------------------
# HTTP-level tests — GET webhook verification
# ---------------------------------------------------------------------------


async def test_webhook_get_correct_token_returns_challenge(client):
    resp = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test_verify_token",
            "hub.challenge": "challenge_abc123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge_abc123"


async def test_webhook_get_wrong_token_returns_403(client):
    resp = await client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "challenge_abc123",
        },
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# HTTP-level test — POST always returns 200
# ---------------------------------------------------------------------------


async def test_webhook_post_returns_200_for_any_payload(client, monkeypatch):
    """POST /webhook must return 200 immediately; the task is mocked here."""
    monkeypatch.setattr("app.routers.webhook.process_inbound_message", MagicMock())
    resp = await client.post("/webhook", json=_inbound_payload())
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Task-logic tests — call the async function directly to avoid nested
# asyncio.run() issues that occur when Celery runs eagerly inside a test loop.
# ---------------------------------------------------------------------------


async def test_inbound_message_is_saved_to_db(db_session, default_org):
    await _process_inbound_message_async(
        _inbound_payload(phone="919111111111", body="Hi there", wa_msg_id="wamid.p4a")
    )

    result = await db_session.execute(
        sa.select(Message)
        .where(Message.contact_phone == "+919111111111")
        .where(Message.direction == MessageDirection.inbound)
    )
    msgs = result.scalars().all()
    assert len(msgs) == 1
    assert msgs[0].body == "Hi there"


async def test_conversation_session_expires_in_24h(db_session, default_org):
    before = datetime.now(timezone.utc)
    await _process_inbound_message_async(
        _inbound_payload(phone="919222222222", body="Hey", wa_msg_id="wamid.p4b")
    )
    after = datetime.now(timezone.utc)

    result = await db_session.execute(
        sa.select(Conversation).where(Conversation.contact_phone == "+919222222222")
    )
    conv = result.scalar_one()
    expires = conv.session_expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    assert (before + timedelta(hours=23, minutes=59)) <= expires
    assert expires <= (after + timedelta(hours=24, minutes=1))


async def test_stop_message_opts_out_contact(db_session, default_org):
    await _process_inbound_message_async(
        _inbound_payload(phone="919333333333", body="STOP", wa_msg_id="wamid.p4c")
    )

    result = await db_session.execute(
        sa.select(Contact).where(Contact.phone == "+919333333333")
    )
    contact = result.scalar_one()
    assert contact.opted_in is False


async def test_status_update_changes_message_status(db_session, default_org):
    # Seed an outbound message with a known wa_message_id
    contact = Contact(organization_id=default_org.id, phone="+919444444444", name="Test", opted_in=True)
    db_session.add(contact)
    await db_session.flush()
    msg = Message(
        organization_id=default_org.id,
        contact_phone="+919444444444",
        direction=MessageDirection.outbound,
        body="Hello from us",
        status=MessageStatus.sent,
        wa_message_id="wamid.outbound001",
    )
    db_session.add(msg)
    await db_session.commit()

    await _process_inbound_message_async(_status_payload("wamid.outbound001", "delivered"))

    # Expire identity-map cache so the next SELECT fetches fresh data from DB
    db_session.expire_all()
    result = await db_session.execute(
        sa.select(Message).where(Message.wa_message_id == "wamid.outbound001")
    )
    updated = result.scalar_one()
    assert updated.status == MessageStatus.delivered


async def test_ai_enabled_saves_outbound_reply(db_session, default_org, mock_claude):
    phone = "+919555555555"
    future = datetime.now(timezone.utc) + timedelta(hours=24)

    # Pre-seed contact + ai-enabled conversation
    contact = Contact(organization_id=default_org.id, phone=phone, name="AI User", opted_in=True)
    db_session.add(contact)
    await db_session.flush()
    conv = Conversation(
        organization_id=default_org.id,
        contact_phone=phone,
        ai_enabled=True,
        session_expires_at=future,
        status=ConversationStatus.active,
    )
    db_session.add(conv)
    await db_session.commit()

    await _process_inbound_message_async(
        _inbound_payload(phone="919555555555", body="What are your hours?", wa_msg_id="wamid.p4d")
    )

    result = await db_session.execute(
        sa.select(Message)
        .where(Message.contact_phone == phone)
        .where(Message.direction == MessageDirection.outbound)
    )
    outbound = result.scalars().all()
    assert len(outbound) == 1
    assert outbound[0].body == "Auto-reply from AI"
