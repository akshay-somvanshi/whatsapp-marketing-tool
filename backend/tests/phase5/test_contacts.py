"""Phase 5 — Contacts API tests."""
from __future__ import annotations

import sqlalchemy as sa

from app.models.contact import Contact


# ---------------------------------------------------------------------------
# POST /contacts
# ---------------------------------------------------------------------------


async def test_create_contact_valid_phone_returns_201(client):
    resp = await client.post(
        "/contacts",
        json={"name": "Priya Sharma", "phone": "+919876543210", "opted_in": True, "tags": ["vip"]},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["phone"] == "+919876543210"
    assert data["name"] == "Priya Sharma"
    assert data["opted_in"] is True
    assert data["tags"] == ["vip"]
    assert "id" in data
    assert "created_at" in data


async def test_create_contact_invalid_phone_returns_422(client):
    resp = await client.post("/contacts", json={"name": "Test", "phone": "not_a_phone"})
    assert resp.status_code == 422


async def test_create_contact_duplicate_phone_returns_409(client, db_session):
    existing = Contact(phone="+919876543210", name="Original", opted_in=False)
    db_session.add(existing)
    await db_session.commit()

    resp = await client.post("/contacts", json={"name": "Duplicate", "phone": "+919876543210"})
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# GET /contacts
# ---------------------------------------------------------------------------


async def test_list_contacts_search_filters_by_name(client, db_session):
    db_session.add_all([
        Contact(phone="+91111111111", name="Priya Sharma", opted_in=True),
        Contact(phone="+91222222222", name="Rahul Kumar", opted_in=True),
    ])
    await db_session.commit()

    resp = await client.get("/contacts", params={"search": "Priya"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Priya Sharma"


async def test_list_contacts_tag_filter_returns_only_tagged(client, db_session):
    db_session.add_all([
        Contact(phone="+91111111111", name="Priya", opted_in=True, tags=["purchased", "vip"]),
        Contact(phone="+91222222222", name="Rahul", opted_in=True, tags=["new"]),
    ])
    await db_session.commit()

    resp = await client.get("/contacts", params={"tags": "purchased"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Priya"


# ---------------------------------------------------------------------------
# POST /contacts/import
# ---------------------------------------------------------------------------


async def test_import_csv_valid_three_rows(client, db_session):
    # Pre-insert one contact that will be upserted (not duplicated)
    db_session.add(Contact(phone="+919876543211", name="Old Name", opted_in=False))
    await db_session.commit()

    csv_body = "phone,name\n+919876543211,New Name\n+919876543212,User B\n+919876543213,User C"
    resp = await client.post(
        "/contacts/import",
        files={"file": ("contacts.csv", csv_body.encode(), "text/csv")},
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["imported"] == 3
    assert payload["skipped"] == 0

    # Total contacts = 3 (upserted A, new B, new C — not 4)
    db_session.expire_all()
    count = (await db_session.execute(sa.select(sa.func.count(Contact.id)))).scalar()
    assert count == 3

    # The upserted contact should have the new name
    result = await db_session.execute(sa.select(Contact).where(Contact.phone == "+919876543211"))
    upserted = result.scalar_one()
    assert upserted.name == "New Name"


async def test_import_csv_missing_phone_column_returns_400(client):
    csv_body = "name,email\nPriya,priya@example.com"
    resp = await client.post(
        "/contacts/import",
        files={"file": ("contacts.csv", csv_body.encode(), "text/csv")},
    )
    assert resp.status_code == 400
