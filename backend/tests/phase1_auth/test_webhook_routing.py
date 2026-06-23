"""Phase 1 — webhook tenant routing by phone_number_id."""
from __future__ import annotations

import uuid

import sqlalchemy as sa

from app.models.message import Message, MessageDirection
from app.models.organization import Organization
from app.tasks.celery_app import _process_inbound_message_async
from tests.conftest import DEFAULT_ORG_PNID


def _inbound_payload(phone_number_id: str, *, phone="919876543210", body="Hello", wa_msg_id="wamid.r1"):
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


async def test_inbound_routed_to_owning_org(db_session, default_org):
    await _process_inbound_message_async(
        _inbound_payload(DEFAULT_ORG_PNID, phone="919876500001", wa_msg_id="wamid.route.a")
    )

    msgs = (
        await db_session.execute(
            sa.select(Message).where(Message.direction == MessageDirection.inbound)
        )
    ).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].organization_id == default_org.id
    assert msgs[0].contact_phone == "+919876500001"


async def test_unknown_phone_number_id_is_dropped(db_session, default_org):
    await _process_inbound_message_async(
        _inbound_payload("unknown_pnid_zzz", phone="919876500002", wa_msg_id="wamid.route.b")
    )

    count = (
        await db_session.execute(sa.select(sa.func.count()).select_from(Message))
    ).scalar_one()
    assert count == 0
