import uuid
from datetime import datetime

import phonenumbers
from pydantic import BaseModel, ConfigDict, field_validator


class ContactCreate(BaseModel):
    name: str
    phone: str
    opted_in: bool = False
    tags: list[str] = []

    @field_validator("phone")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        try:
            parsed = phonenumbers.parse(v)
        except phonenumbers.NumberParseException as exc:
            raise ValueError(str(exc)) from exc
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("not a valid phone number")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str
    opted_in: bool
    tags: list[str]
    created_at: datetime
