"""Cryptographic primitives: password hashing, access JWTs, opaque random tokens.

Pure functions with no database access, so any module can use them.
See docs/architecture/07-security.md, section 7.2.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from app.core.config import get_settings

logger = logging.getLogger("app.core.security")

# ---------------------------------------------------------------- passwords

_hasher = PasswordHasher()  # Argon2id with the library's current recommended parameters
# Verified against when the account does not exist, so "no such user" takes as long
# as "wrong password" and response time does not reveal which emails are registered.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# ---------------------------------------------------------------- opaque tokens


def new_token() -> str:
    """Random URL-safe token (refresh tokens, CSRF tokens). 256 bits."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Only this hash is stored, so a database leak does not leak usable tokens."""
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


# ---------------------------------------------------------------- access JWT (EdDSA)

ALGORITHM = "EdDSA"


@dataclass(frozen=True)
class AccessClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID
    expires_at: datetime


class InvalidAccessToken(Exception):
    pass


@lru_cache
def _signing_key() -> Ed25519PrivateKey:
    raw = get_settings().jwt_signing_key
    if not raw:
        logger.warning("JWT_SIGNING_KEY is empty: using a throwaway key for this process")
        return Ed25519PrivateKey.generate()
    seed = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(seed) != 32:
        raise ValueError("JWT_SIGNING_KEY must decode to exactly 32 bytes")
    return Ed25519PrivateKey.from_private_bytes(seed)


def _verify_key() -> Ed25519PublicKey:
    return _signing_key().public_key()


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> tuple[str, int]:
    """Returns (token, lifetime in seconds)."""
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "iss": s.jwt_issuer,
        "sub": str(user_id),
        "sid": str(session_id),
        "typ": "access",
        "iat": now,
        "exp": now + timedelta(seconds=s.access_token_ttl_seconds),
    }
    token = jwt.encode(payload, _signing_key(), algorithm=ALGORITHM, headers={"kid": s.jwt_key_id})
    return token, s.access_token_ttl_seconds


def decode_access_token(token: str) -> AccessClaims:
    s = get_settings()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("kid") != s.jwt_key_id:
            raise InvalidAccessToken("unknown key id")
        data = jwt.decode(
            token,
            _verify_key(),
            algorithms=[ALGORITHM],
            issuer=s.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "sid", "iss"]},
        )
        if data.get("typ") != "access":
            raise InvalidAccessToken("not an access token")
        return AccessClaims(
            user_id=uuid.UUID(data["sub"]),
            session_id=uuid.UUID(data["sid"]),
            expires_at=datetime.fromtimestamp(data["exp"], UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidAccessToken(str(exc)) from exc
