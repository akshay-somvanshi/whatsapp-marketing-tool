"""Phase 1 — organization settings & member management tests."""
from __future__ import annotations

import uuid

from app.models.organization import Organization
from app.models.user import Membership, Role, User
from app.security import hash_password


async def test_get_org_masks_secrets(client, default_org):
    resp = await client.get("/org")
    assert resp.status_code == 200
    body = resp.json()
    # Secrets are never returned — only boolean "set" flags.
    assert "whatsapp_api_token" not in body
    assert "anthropic_api_key" not in body
    assert body["whatsapp_api_token_set"] is False
    assert body["whatsapp_phone_number_id"] == "test_pnid_default"


async def test_update_org_settings(client):
    resp = await client.patch(
        "/org",
        json={"name": "Renamed", "anthropic_api_key": "sk-test", "ai_provider": "anthropic"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["anthropic_api_key_set"] is True


async def test_update_org_invalid_provider_rejected(client):
    resp = await client.patch("/org", json={"ai_provider": "not_a_provider"})
    assert resp.status_code == 422


async def test_duplicate_phone_number_id_returns_409(client, db_session, default_org, make_token):
    # Seed a second org that owns a specific phone_number_id.
    other = Organization(name="Other", slug=f"other-{uuid.uuid4().hex[:6]}",
                         whatsapp_phone_number_id="pnid_taken")
    db_session.add(other)
    await db_session.commit()

    # default_org tries to claim the same phone_number_id → 409, not 500.
    resp = await client.patch("/org", json={"whatsapp_phone_number_id": "pnid_taken"})
    assert resp.status_code == 409


async def test_owner_add_update_remove_member(client, default_org, db_session):
    # Add a new agent member.
    added = await client.post(
        "/org/members",
        json={"email": "member@test.com", "role": "agent", "password": "password123"},
    )
    assert added.status_code == 201
    user_id = added.json()["user_id"]

    # Promote to admin.
    promoted = await client.patch(f"/org/members/{user_id}", json={"role": "admin"})
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    # Listing shows owner + the new member.
    members = await client.get("/org/members")
    assert members.status_code == 200
    assert len(members.json()) == 2

    # Remove the member.
    removed = await client.delete(f"/org/members/{user_id}")
    assert removed.status_code == 204


async def test_cannot_remove_owner(client, default_org):
    resp = await client.delete(f"/org/members/{default_org._owner_id}")
    # Owner cannot remove themselves.
    assert resp.status_code == 400
