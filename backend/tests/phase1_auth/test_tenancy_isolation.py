"""Phase 1 — cross-tenant isolation tests."""
from __future__ import annotations

import uuid

from app.models.organization import Organization
from app.models.user import Membership, Role, User
from app.security import hash_password


async def _seed_org(db_session, *, slug: str, email: str, role: Role = Role.owner):
    org = Organization(name=slug, slug=f"{slug}-{uuid.uuid4().hex[:6]}")
    user = User(email=email, password_hash=hash_password("password123"))
    db_session.add_all([org, user])
    await db_session.flush()
    db_session.add(Membership(user_id=user.id, organization_id=org.id, role=role))
    await db_session.commit()
    return org, user


async def test_same_phone_allowed_across_orgs(client, db_session, default_org, make_token):
    org_b, user_b = await _seed_org(db_session, slug="org-b", email="b@test.com")
    headers_b = {"Authorization": f"Bearer {make_token(user_b.id, org_b.id, 'owner')}"}

    phone = "+919999900001"
    # Default org (A) creates the contact (client is authed as A's owner).
    a = await client.post("/contacts", json={"name": "A Contact", "phone": phone})
    assert a.status_code == 201
    # Org B creates a contact with the SAME phone — must be allowed.
    b = await client.post("/contacts", json={"name": "B Contact", "phone": phone}, headers=headers_b)
    assert b.status_code == 201


async def test_list_is_scoped_to_org(client, db_session, default_org, make_token):
    org_b, user_b = await _seed_org(db_session, slug="org-b2", email="b2@test.com")
    headers_b = {"Authorization": f"Bearer {make_token(user_b.id, org_b.id, 'owner')}"}

    await client.post("/contacts", json={"name": "Only A", "phone": "+919999900010"})

    list_a = await client.get("/contacts")
    list_b = await client.get("/contacts", headers=headers_b)
    assert {c["phone"] for c in list_a.json()} == {"+919999900010"}
    assert list_b.json() == []


async def test_cross_org_get_patch_delete_returns_404(client, db_session, default_org, make_token):
    org_b, user_b = await _seed_org(db_session, slug="org-b3", email="b3@test.com")
    headers_b = {"Authorization": f"Bearer {make_token(user_b.id, org_b.id, 'owner')}"}

    created = await client.post("/contacts", json={"name": "A only", "phone": "+919999900020"})
    contact_id = created.json()["id"]

    # Org B must not be able to mutate org A's contact.
    patch = await client.patch(
        f"/contacts/{contact_id}", json={"name": "hacked"}, headers=headers_b
    )
    assert patch.status_code == 404
    delete = await client.delete(f"/contacts/{contact_id}", headers=headers_b)
    assert delete.status_code == 404


async def test_campaign_scoped_to_org(client, db_session, default_org, make_token):
    org_b, user_b = await _seed_org(db_session, slug="org-b4", email="b4@test.com")
    headers_b = {"Authorization": f"Bearer {make_token(user_b.id, org_b.id, 'owner')}"}

    created = await client.post(
        "/campaigns",
        json={"name": "A Campaign", "template_name": "hello_world"},
    )
    assert created.status_code == 201
    campaign_id = created.json()["id"]

    # B cannot see or fetch A's campaign.
    assert (await client.get("/campaigns", headers=headers_b)).json() == []
    assert (await client.get(f"/campaigns/{campaign_id}", headers=headers_b)).status_code == 404
