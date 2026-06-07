"""Phase 6 — Campaigns API and Celery task tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact
from app.models.conversation import Conversation, ConversationStatus
from app.models.message import Message, MessageDirection
from app.tasks.celery_app import (
    _check_session_expiry_async,
    _send_campaign_async,
    _trigger_post_purchase_async,
)


# ---------------------------------------------------------------------------
# POST /campaigns
# ---------------------------------------------------------------------------


async def test_create_campaign_valid_template_returns_201(client):
    resp = await client.post(
        "/campaigns",
        json={
            "name": "Summer Sale",
            "template_name": "review_request",
            "audience_tags": ["purchased"],
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "draft"
    assert data["sent_count"] == 0
    assert data["delivered_count"] == 0
    assert data["read_count"] == 0
    assert data["template_name"] == "review_request"


async def test_create_campaign_unknown_template_returns_422(client):
    resp = await client.post(
        "/campaigns",
        json={"name": "Bad Campaign", "template_name": "nonexistent_template"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /campaigns
# ---------------------------------------------------------------------------


async def test_list_campaigns_includes_stat_fields(client):
    await client.post(
        "/campaigns",
        json={"name": "Campaign A", "template_name": "review_request"},
    )

    resp = await client.get("/campaigns")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert "sent_count" in data[0]
    assert "delivered_count" in data[0]
    assert "read_count" in data[0]


# ---------------------------------------------------------------------------
# send_campaign_task
# ---------------------------------------------------------------------------


async def test_send_campaign_sends_to_opted_in_skips_opted_out(db_session):
    db_session.add_all([
        Contact(phone="+919876543210", name="Priya", opted_in=True, tags=["purchased"]),
        Contact(phone="+919876543211", name="Rahul", opted_in=False, tags=["purchased"]),
    ])
    await db_session.flush()
    campaign = Campaign(
        name="Test Campaign",
        template_name="review_request",
        audience_tags=["purchased"],
    )
    db_session.add(campaign)
    await db_session.commit()

    campaign_id = campaign.id
    await _send_campaign_async(str(campaign_id))

    db_session.expire_all()
    updated = (
        await db_session.execute(sa.select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one()
    assert updated.sent_count == 1
    assert updated.status == CampaignStatus.completed


async def test_send_campaign_no_matching_contacts_completes_with_zero(db_session):
    campaign = Campaign(
        name="Empty Campaign",
        template_name="review_request",
        audience_tags=["no_such_tag"],
    )
    db_session.add(campaign)
    await db_session.commit()

    campaign_id = campaign.id
    await _send_campaign_async(str(campaign_id))

    db_session.expire_all()
    updated = (
        await db_session.execute(sa.select(Campaign).where(Campaign.id == campaign_id))
    ).scalar_one()
    assert updated.sent_count == 0
    assert updated.status == CampaignStatus.completed


# ---------------------------------------------------------------------------
# check_session_expiry_task
# ---------------------------------------------------------------------------


async def test_check_session_expiry_marks_past_conversations_expired(db_session):
    contact = Contact(phone="+919876543210", name="Test", opted_in=True)
    db_session.add(contact)
    await db_session.flush()

    conv = Conversation(
        contact_phone="+919876543210",
        session_expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        status=ConversationStatus.active,
    )
    db_session.add(conv)
    await db_session.commit()

    await _check_session_expiry_async()

    db_session.expire_all()
    updated = (await db_session.execute(sa.select(Conversation))).scalar_one()
    assert updated.status == ConversationStatus.expired


# ---------------------------------------------------------------------------
# trigger_post_purchase_task
# ---------------------------------------------------------------------------


async def test_trigger_post_purchase_sends_and_does_not_double_send(db_session):
    contact = Contact(
        phone="+919876543210",
        name="Priya",
        opted_in=True,
        tags=["purchased"],
    )
    db_session.add(contact)
    await db_session.commit()

    # First call: should send one review_request
    await _trigger_post_purchase_async()

    db_session.expire_all()
    msgs = (
        await db_session.execute(
            sa.select(Message).where(Message.template_name == "review_request")
        )
    ).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].direction == MessageDirection.outbound

    # Second call: must not double-send
    await _trigger_post_purchase_async()

    db_session.expire_all()
    msgs = (
        await db_session.execute(
            sa.select(Message).where(Message.template_name == "review_request")
        )
    ).scalars().all()
    assert len(msgs) == 1
