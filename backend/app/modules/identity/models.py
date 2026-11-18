"""Tables of the `identity` module (docs/architecture/03-database-er.md, 3.1).

The password is not a column of ``users``: it lives in ``user_credentials`` (type
``password``), so V3 adds TOTP and passkeys as new credential types without touching users.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.models import Timestamps, UUIDPrimaryKey

USER_STATUSES = ("active", "blocked", "pending")
LOCALES = ("uz", "ru", "en")
CREDENTIAL_TYPES = ("password", "totp", "webauthn")
ROLE_SCOPES = ("platform", "store")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _user_fk(ondelete: str = "CASCADE") -> ForeignKey:
    return ForeignKey("users.id", ondelete=ondelete)


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="contact_required"),
        CheckConstraint(_in("status", USER_STATUSES), name="status"),
        CheckConstraint(_in("locale", LOCALES), name="locale"),
    )

    email: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    phone: Mapped[str | None] = mapped_column(String(16), unique=True)  # E.164
    full_name: Mapped[str] = mapped_column(String(200), default="", server_default="")
    locale: Mapped[str] = mapped_column(String(2), default="uz", server_default="uz")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserCredential(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "user_credentials"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        CheckConstraint(_in("type", CREDENTIAL_TYPES), name="type"),
        # One password per user; TOTP / passkeys may have several entries.
        Index(
            "uq_user_credentials_one_password",
            "user_id",
            unique=True,
            postgresql_where=text("type = 'password'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _user_fk(), index=True)
    type: Mapped[str] = mapped_column(String(16))
    secret: Mapped[str] = mapped_column(String(255))  # password: Argon2id hash
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "roles"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (CheckConstraint(_in("scope", ROLE_SCOPES), name="scope"),)

    code: Mapped[str] = mapped_column(String(64), unique=True)
    scope: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(255), default="", server_default="")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))


class Permission(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "permissions"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    code: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="", server_default="")


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    """Platform-scope roles only. Store roles come from store memberships."""

    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _user_fk(), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), _user_fk("SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(UUIDPrimaryKey, Timestamps, Base):
    """A signed-in device. Revoking it logs that device out at once."""

    __tablename__ = "sessions"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _user_fk(), index=True)
    device_info: Mapped[str] = mapped_column(String(255), default="", server_default="")
    ip: Mapped[str | None] = mapped_column(INET)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoke_reason: Mapped[str | None] = mapped_column(String(32))


class RefreshToken(UUIDPrimaryKey, Timestamps, Base):
    """One link of a session's rotation chain. Only the SHA-256 of the token is stored."""

    __tablename__ = "refresh_tokens"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class Address(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "addresses"
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012
    __table_args__ = (
        Index(
            "uq_addresses_one_default",
            "user_id",
            unique=True,
            postgresql_where=text("is_default AND deleted_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), _user_fk(), index=True)
    recipient_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(16))
    region: Mapped[str] = mapped_column(String(100))
    city: Mapped[str] = mapped_column(String(100))
    line1: Mapped[str] = mapped_column(String(255))
    line2: Mapped[str | None] = mapped_column(String(255))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
