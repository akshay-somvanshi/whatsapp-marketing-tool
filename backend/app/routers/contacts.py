import csv
import io
import uuid

import phonenumbers
import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.dialects.postgresql import array as pg_array
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contact import Contact
from app.schemas.contact import ContactCreate, ContactOut

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _parse_e164(raw: str) -> str:
    try:
        parsed = phonenumbers.parse(raw)
    except phonenumbers.NumberParseException as exc:
        raise ValueError(str(exc)) from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("not a valid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


@router.post("", response_model=ContactOut, status_code=201)
async def create_contact(data: ContactCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(sa.select(Contact).where(Contact.phone == data.phone))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Contact with this phone already exists")

    contact = Contact(name=data.name, phone=data.phone, opted_in=data.opted_in, tags=data.tags)
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    search: str | None = Query(default=None),
    tags: list[str] = Query(default=[]),
    db: AsyncSession = Depends(get_db),
):
    stmt = sa.select(Contact).order_by(Contact.created_at.desc())

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(sa.or_(Contact.name.ilike(pattern), Contact.phone.ilike(pattern)))

    if tags:
        # ANY(contacts.tags) avoids the text[] vs varchar[] type-mismatch of the && operator
        stmt = stmt.where(
            sa.or_(*(sa.literal(t) == sa.func.any(Contact.tags) for t in tags))
        )

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/import")
async def import_contacts(file: UploadFile, db: AsyncSession = Depends(get_db)):
    content = await file.read()
    text = content.decode("utf-8-sig")  # strips UTF-8 BOM if present
    reader = csv.DictReader(io.StringIO(text))

    fieldnames = list(reader.fieldnames or [])
    if "phone" not in fieldnames:
        raise HTTPException(status_code=400, detail="CSV must contain a 'phone' column")

    imported = skipped = 0

    for row in reader:
        raw_phone = (row.get("phone") or "").strip()
        try:
            phone = _parse_e164(raw_phone)
        except ValueError:
            skipped += 1
            continue

        name = (row.get("name") or "").strip() or phone
        opted_in = (row.get("opted_in") or "false").strip().lower() in ("true", "1", "yes")
        tags_raw = (row.get("tags") or "").strip()
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        ins = pg_insert(Contact).values(
            id=uuid.uuid4(), phone=phone, name=name, opted_in=opted_in, tags=tags
        )
        await db.execute(
            ins.on_conflict_do_update(
                index_elements=["phone"],
                set_={"name": ins.excluded.name, "opted_in": ins.excluded.opted_in, "tags": ins.excluded.tags},
            )
        )
        imported += 1

    await db.commit()
    return {"imported": imported, "skipped": skipped}
