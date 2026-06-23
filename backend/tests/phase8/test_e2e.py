"""
Phase 9 — End-to-end golden path.

Exercises the full marketing loop in a single test transaction against the
real wa_test database (mock WhatsApp, mock Claude):

  1.  POST /contacts        → contact created, opted in
  2.  POST /campaigns       → campaign created (draft)
  3.  send_campaign_task    → template message sent, sent_count = 1
  4.  inbound webhook       → customer reply saved, AI auto-reply saved
  5.  GET /conversations    → active conversation appears in API response
  6.  STOP webhook          → contact opted out
  7.  POST /campaigns again → follow-up campaign skips opted-out contact (0 sent)
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection
from app.tasks.celery_app import _process_inbound_message_async, _send_campaign_async
from tests.conftest import DEFAULT_ORG_PNID


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PHONE = "+919876543210"
RAW_PHONE = "919876543210"  # as Meta delivers it (no leading +)


def _inbound_payload(body: str, wa_msg_id: str) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": DEFAULT_ORG_PNID},
                            "messages": [
                                {
                                    "from": RAW_PHONE,
                                    "id": wa_msg_id,
                                    "text": {"body": body},
                                    "type": "text",
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


# ---------------------------------------------------------------------------
# Golden path — single test covering all eight plan steps
# ---------------------------------------------------------------------------


async def test_golden_path_full_flow(client, db_session, mock_claude):
    # ── 1. Create contact via REST API ───────────────────────────────────────
    resp = await client.post(
        "/contacts",
        json={"name": "Priya Sharma", "phone": PHONE, "opted_in": True, "tags": ["purchased"]},
    )
    assert resp.status_code == 201
    assert resp.json()["opted_in"] is True

    # ── 2. Create campaign via REST API ──────────────────────────────────────
    resp = await client.post(
        "/campaigns",
        json={
            "name": "Post-Purchase Review",
            "template_name": "review_request",
            "audience_tags": ["purchased"],
        },
    )
    assert resp.status_code == 201
    campaign_id_str = resp.json()["id"]
    assert resp.json()["status"] == "draft"

    # ── 3. Fan-out campaign (called directly to avoid nested asyncio.run) ────
    await _send_campaign_async(campaign_id_str)

    # ── 4. Outbound template message saved, campaign stats updated ───────────
    db_session.expire_all()

    outbound = (
        await db_session.execute(
            sa.select(Message).where(
                Message.contact_phone == PHONE,
                Message.direction == MessageDirection.outbound,
            )
        )
    ).scalars().all()
    assert len(outbound) == 1
    assert outbound[0].template_name == "review_request"

    campaign = (
        await db_session.execute(
            sa.select(Campaign).where(Campaign.id == uuid.UUID(campaign_id_str))
        )
    ).scalar_one()
    assert campaign.sent_count == 1
    assert campaign.status == CampaignStatus.completed

    # ── 5. Customer sends an inbound reply ───────────────────────────────────
    await _process_inbound_message_async(
        _inbound_payload("Which gold bangle is available?", "wamid.reply001")
    )

    # ── 6. Inbound saved, AI auto-reply saved, conversation is active ────────
    db_session.expire_all()

    inbound = (
        await db_session.execute(
            sa.select(Message).where(
                Message.contact_phone == PHONE,
                Message.direction == MessageDirection.inbound,
            )
        )
    ).scalars().all()
    assert len(inbound) == 1
    assert inbound[0].body == "Which gold bangle is available?"

    # AI reply is outbound with no template_name (distinguishes it from campaign msg)
    ai_replies = (
        await db_session.execute(
            sa.select(Message).where(
                Message.contact_phone == PHONE,
                Message.direction == MessageDirection.outbound,
                Message.template_name.is_(None),
            )
        )
    ).scalars().all()
    assert len(ai_replies) == 1
    assert ai_replies[0].body == "Auto-reply from AI"

    conv = (
        await db_session.execute(
            sa.select(Conversation).where(Conversation.contact_phone == PHONE)
        )
    ).scalar_one()
    assert conv.status == ConversationStatus.active

    # ── 6b. Active conversation appears in GET /conversations ────────────────
    resp = await client.get("/conversations")
    assert resp.status_code == 200
    phones = [c["contact_phone"] for c in resp.json()]
    assert PHONE in phones

    # ── 7. Customer sends STOP ───────────────────────────────────────────────
    await _process_inbound_message_async(
        _inbound_payload("STOP", "wamid.stop001")
    )

    # ── 8. Contact is opted out ───────────────────────────────────────────────
    db_session.expire_all()

    contact = (
        await db_session.execute(sa.select(Contact).where(Contact.phone == PHONE))
    ).scalar_one()
    assert contact.opted_in is False

    # ── 8b. Follow-up campaign skips opted-out contact (0 sent) ──────────────
    resp = await client.post(
        "/campaigns",
        json={
            "name": "Follow-up Campaign",
            "template_name": "review_request",
            "audience_tags": ["purchased"],
        },
    )
    assert resp.status_code == 201
    followup_id_str = resp.json()["id"]

    await _send_campaign_async(followup_id_str)

    db_session.expire_all()

    followup = (
        await db_session.execute(
            sa.select(Campaign).where(Campaign.id == uuid.UUID(followup_id_str))
        )
    ).scalar_one()
    assert followup.sent_count == 0
    assert followup.status == CampaignStatus.completed


# ---------------------------------------------------------------------------
# Status update flows
# ---------------------------------------------------------------------------


async def test_delivery_status_update_propagates(client, db_session, default_org):
    """Webhook status updates (delivered/read) are reflected on the message row."""
    # Seed an outbound message via the contact + message models directly
    contact = Contact(organization_id=default_org.id, phone=PHONE, name="Test", opted_in=True)
    db_session.add(contact)
    await db_session.flush()

    msg = Message(
        organization_id=default_org.id,
        contact_phone=PHONE,
        direction=MessageDirection.outbound,
        body="[review_request]",
        status="sent",
        wa_message_id="wamid.track001",
        template_name="review_request",
    )
    db_session.add(msg)
    await db_session.commit()

    # Simulate Meta sending delivered → then read status updates
    for status in ("delivered", "read"):
        await _process_inbound_message_async(
            {
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "metadata": {"phone_number_id": DEFAULT_ORG_PNID},
                                    "statuses": [
                                        {
                                            "id": "wamid.track001",
                                            "status": status,
                                            "timestamp": "1700000001",
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ]
            }
        )

    db_session.expire_all()
    updated = (
        await db_session.execute(
            sa.select(Message).where(Message.wa_message_id == "wamid.track001")
        )
    ).scalar_one()
    assert updated.status == "read"


# ---------------------------------------------------------------------------
# Multi-contact campaign
# ---------------------------------------------------------------------------


async def test_campaign_fanout_multiple_opted_in_contacts(client, db_session):
    """Campaign fans out to all opted-in contacts matching the tag."""
    phones = ["+919876543210", "+919876543211", "+919876543212"]
    for i, phone in enumerate(phones):
        opted_in = i < 2  # first two opted in, third opted out
        await client.post(
            "/contacts",
            json={"name": f"Contact {i}", "phone": phone, "opted_in": opted_in, "tags": ["vip"]},
        )

    resp = await client.post(
        "/campaigns",
        json={"name": "VIP Campaign", "template_name": "review_request", "audience_tags": ["vip"]},
    )
    assert resp.status_code == 201
    campaign_id_str = resp.json()["id"]

    await _send_campaign_async(campaign_id_str)

    db_session.expire_all()
    campaign = (
        await db_session.execute(
            sa.select(Campaign).where(Campaign.id == uuid.UUID(campaign_id_str))
        )
    ).scalar_one()
    assert campaign.sent_count == 2  # only two opted-in contacts
    assert campaign.status == CampaignStatus.completed

    msgs = (
        await db_session.execute(
            sa.select(Message).where(Message.direction == MessageDirection.outbound)
        )
    ).scalars().all()
    assert len(msgs) == 2
