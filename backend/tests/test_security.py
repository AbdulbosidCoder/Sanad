import uuid

import jwt
import pytest

from app.core.models import uuid7
from app.core.security import (
    InvalidAccessToken,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_uuid7_has_version_7_and_sorts_by_time():
    ids = [uuid7() for _ in range(50)]
    assert all(i.version == 7 and i.variant == uuid.RFC_4122 for i in ids)
    assert ids == sorted(ids, key=lambda i: i.int >> 80)  # timestamp prefix never goes back


def test_password_hash_roundtrip():
    h = hash_password("correct-horse")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct-horse")
    assert not verify_password(h, "wrong")
    assert not verify_password(None, "anything")
    assert not verify_password("garbage", "anything")


def test_token_hash_is_stable_and_not_the_token():
    assert hash_token("abc") == hash_token("abc") != "abc"
    assert len(hash_token("abc")) == 64


def test_access_token_roundtrip():
    user, session = uuid7(), uuid7()
    token, ttl = create_access_token(user, session)
    claims = decode_access_token(token)
    assert (claims.user_id, claims.session_id) == (user, session)
    assert ttl == 15 * 60


def test_tampered_access_token_is_rejected():
    token, _ = create_access_token(uuid7(), uuid7())
    header, payload, signature = token.split(".")
    # Change a character in the middle: the last ones carry padding bits and may not
    # change the decoded bytes, which made this test fail about once in 256 runs.
    middle = len(signature) // 2
    swapped = "B" if signature[middle] == "A" else "A"
    forged = f"{header}.{payload}.{signature[:middle]}{swapped}{signature[middle + 1 :]}"
    with pytest.raises(InvalidAccessToken):
        decode_access_token(forged)


def test_unsigned_and_foreign_tokens_are_rejected():
    claims = {"sub": str(uuid7()), "sid": str(uuid7()), "typ": "access", "iss": "sanad"}
    unsigned = jwt.encode(claims, key=None, algorithm="none")
    with pytest.raises(InvalidAccessToken):
        decode_access_token(unsigned)
    hs = jwt.encode(claims, "secret-secret-secret-secret-1234", algorithm="HS256")
    with pytest.raises(InvalidAccessToken):
        decode_access_token(hs)
