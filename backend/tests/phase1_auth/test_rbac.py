"""Phase 1 — role-based access control tests."""
from __future__ import annotations

import uuid

from app.models.user import Membership, Role, User
from app.security import hash_password


async def _add_member(db_session, org_id, *, email: str, role: Role):
    user = User(email=email, password_hash=hash_password("password123"))
    db_session.add(user)
    await db_session.flush()
    db_session.add(Membership(user_id=user.id, organization_id=org_id, role=role))
    await db_session.commit()
    return user


async def test_agent_can_read_but_not_write_contacts(client, db_session, default_org, make_token):
    agent = await _add_member(db_session, default_org.id, email="agent@test.com", role=Role.agent)
    headers = {"Authorization": f"Bearer {make_token(agent.id, default_org.id, 'agent')}"}

    # Read allowed.
    assert (await client.get("/contacts", headers=headers)).status_code == 200
    # Write forbidden.
    create = await client.post(
        "/contacts", json={"name": "X", "phone": "+919999900030"}, headers=headers
    )
    assert create.status_code == 403


async def test_admin_can_write_contacts(client, db_session, default_org, make_token):
    admin = await _add_member(db_session, default_org.id, email="admin@test.com", role=Role.admin)
    headers = {"Authorization": f"Bearer {make_token(admin.id, default_org.id, 'admin')}"}

    create = await client.post(
        "/contacts", json={"name": "Y", "phone": "+919999900031"}, headers=headers
    )
    assert create.status_code == 201


async def test_agent_cannot_create_campaign(client, db_session, default_org, make_token):
    agent = await _add_member(db_session, default_org.id, email="agent2@test.com", role=Role.agent)
    headers = {"Authorization": f"Bearer {make_token(agent.id, default_org.id, 'agent')}"}

    resp = await client.post(
        "/campaigns",
        json={"name": "Nope", "template_name": "hello_world"},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_only_owner_can_add_members(client, db_session, default_org, make_token):
    admin = await _add_member(db_session, default_org.id, email="admin2@test.com", role=Role.admin)
    admin_headers = {"Authorization": f"Bearer {make_token(admin.id, default_org.id, 'admin')}"}

    # Admin is blocked from member management.
    blocked = await client.post(
        "/org/members",
        json={"email": "new@test.com", "role": "agent", "password": "password123"},
        headers=admin_headers,
    )
    assert blocked.status_code == 403

    # Owner (default client auth) can add a member.
    ok = await client.post(
        "/org/members",
        json={"email": "new@test.com", "role": "agent", "password": "password123"},
    )
    assert ok.status_code == 201
    assert ok.json()["role"] == "agent"


async def test_owner_role_cannot_be_assigned(client, default_org):
    resp = await client.post(
        "/org/members",
        json={"email": "boss@test.com", "role": "owner", "password": "password123"},
    )
    assert resp.status_code == 422
