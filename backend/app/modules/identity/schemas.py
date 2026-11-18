"""Request and response bodies of the `identity` API.

Input models forbid unknown fields (mass-assignment protection, docs 07-security.md):
status, roles or verification flags can never be set through these bodies.
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

Locale = Literal["uz", "ru", "en"]

_PHONE_SEPARATORS = re.compile(r"[\s\-().]")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(value: str) -> str:
    """``+998 (90) 123-45-67`` -> ``+998901234567``. Only E.164 with a leading ``+``."""
    phone = _PHONE_SEPARATORS.sub("", value)
    if not _E164.fullmatch(phone):
        raise ValueError("phone must be in international format, e.g. +998901234567")
    return phone


Phone = Annotated[str, AfterValidator(normalize_phone)]
Password = Annotated[str, Field(min_length=8, max_length=128)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth


class RegisterIn(_In):
    email: EmailStr | None = None
    phone: Phone | None = None
    password: Password
    full_name: Name = ""
    locale: Locale = "uz"

    @model_validator(mode="after")
    def _contact_required(self) -> Self:
        if self.email is None and self.phone is None:
            raise ValueError("email or phone is required")
        return self


class LoginIn(_In):
    login: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=254)]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenOut(BaseModel):
    """Login result. ``next_step`` is reserved for multi-step login (V3: ``"otp"``);
    while it is null the tokens are final. The refresh token is only in the HttpOnly cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - a scheme name, not a secret
    expires_in: int
    csrf_token: str = Field(description="Send back as X-CSRF-Token to /auth/refresh and /logout")
    next_step: str | None = None


# ---------------------------------------------------------------- profile


class MeOut(_Out):
    id: uuid.UUID
    email: str | None
    phone: str | None
    full_name: str
    locale: Locale
    status: str
    email_verified: bool
    phone_verified: bool
    created_at: datetime
    roles: list[str]
    permissions: list[str]


class MeUpdate(_In):
    full_name: Name | None = None
    locale: Locale | None = None


class PasswordChangeIn(_In):
    current_password: Annotated[str, Field(min_length=1, max_length=128)]
    new_password: Password


class SessionOut(_Out):
    id: uuid.UUID
    device_info: str
    ip: str | None
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    current: bool


# ---------------------------------------------------------------- addresses


class AddressIn(_In):
    recipient_name: Line
    phone: Phone
    region: Short
    city: Short
    line1: Line
    line2: Line | None = None
    is_default: bool = False


class AddressUpdate(_In):
    recipient_name: Line | None = None
    phone: Phone | None = None
    region: Short | None = None
    city: Short | None = None
    line1: Line | None = None
    line2: Line | None = None
    is_default: Literal[True] | None = Field(
        default=None, description="Only true is accepted: make this the default address"
    )


class AddressOut(_Out):
    id: uuid.UUID
    recipient_name: str
    phone: str
    region: str
    city: str
    line1: str
    line2: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime
