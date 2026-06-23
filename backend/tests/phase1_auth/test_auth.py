"""Phase 1 (multi-tenancy & auth) — authentication tests."""
from __future__ import annotations

import sqlalchemy as sa

from app.models.organization import Organization
from app.models.user import Membership, Role, User


async def test_register_creates_user_org_and_owner(client, db_session):
    resp = await client.post(
        "/auth/register",
        json={
            "email": "Founder@Example.com",
            "password": "supersecret",
            "full_name": "Founder",
            "organization_name": "Acme Jewels",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]

    # Email normalized to lowercase; org + owner membership exist.
    user = (
        await db_session.execute(sa.select(User).where(User.email == "founder@example.com"))
    ).scalar_one()
    org = (
        await db_session.execute(sa.select(Organization).where(Organization.name == "Acme Jewels"))
    ).scalar_one()
    membership = (
        await db_session.execute(
            sa.select(Membership).where(
                Membership.user_id == user.id, Membership.organization_id == org.id
            )
        )
    ).scalar_one()
    assert membership.role == Role.owner


async def test_register_duplicate_email_returns_409(client):
    payload = {
        "email": "dup@example.com",
        "password": "supersecret",
        "organization_name": "Org One",
    }
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json={**payload, "organization_name": "Org Two"})
    assert second.status_code == 409


async def test_register_weak_password_returns_422(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "short", "organization_name": "Org"},
    )
    assert resp.status_code == 422


async def test_login_correct_and_incorrect(client):
    await client.post(
        "/auth/register",
        json={"email": "login@example.com", "password": "supersecret", "organization_name": "Org"},
    )
    ok = await client.post(
        "/auth/login", json={"email": "login@example.com", "password": "supersecret"}
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]

    bad = await client.post(
        "/auth/login", json={"email": "login@example.com", "password": "wrongpass"}
    )
    assert bad.status_code == 401


async def test_refresh_issues_new_access_token(client):
    reg = await client.post(
        "/auth/register",
        json={"email": "refresh@example.com", "password": "supersecret", "organization_name": "Org"},
    )
    refresh_token = reg.json()["refresh_token"]
    resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_refresh_rejects_access_token(client):
    reg = await client.post(
        "/auth/register",
        json={"email": "wrongtype@example.com", "password": "supersecret", "organization_name": "Org"},
    )
    access_token = reg.json()["access_token"]
    # An access token must not be accepted where a refresh token is required.
    resp = await client.post("/auth/refresh", json={"refresh_token": access_token})
    assert resp.status_code == 401


async def test_me_returns_user_without_password(client, default_org):
    resp = await client.get("/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "owner@test.com"
    assert "password_hash" not in body
    assert "password" not in body
    assert len(body["memberships"]) == 1
    assert body["memberships"][0]["role"] == "owner"


async def test_protected_endpoints_require_auth(client):
    # Strip the default Authorization header.
    for path in ("/contacts", "/campaigns", "/conversations", "/auth/me", "/org"):
        resp = await client.get(path, headers={"Authorization": ""})
        assert resp.status_code == 401, f"{path} should require auth"
