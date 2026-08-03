from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_password_hash_is_verifiable() -> None:
    encoded = hash_password("long-enough-password")

    assert encoded != "long-enough-password"
    assert verify_password("long-enough-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_token_round_trip() -> None:
    user_id = uuid4()

    token = create_access_token(user_id, "customer")
    claims = decode_access_token(token)

    assert claims.sub == user_id
    assert claims.role == "customer"
    assert claims.iat < claims.exp


def test_invalid_token_is_translated_to_app_error() -> None:
    with pytest.raises(AppError) as raised:
        decode_access_token("not-a-token")

    assert raised.value.code == "invalid_token"
    assert raised.value.message == "Invalid or expired access token"
    assert raised.value.status_code == 401
    assert raised.value.details == {}


@pytest.mark.parametrize(
    "claims",
    [
        {
            "role": "customer",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=1),
        },
        {
            "sub": str(uuid4()),
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=1),
        },
        {"sub": str(uuid4()), "role": "customer", "exp": datetime.now(UTC) + timedelta(minutes=1)},
        {"sub": str(uuid4()), "role": "customer", "iat": datetime.now(UTC)},
        {
            "sub": str(uuid4()),
            "role": "customer",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        {
            "sub": "not-a-uuid",
            "role": "customer",
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=1),
        },
        {
            "sub": str(uuid4()),
            "role": 42,
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=1),
        },
    ],
    ids=[
        "missing-sub",
        "missing-role",
        "missing-iat",
        "missing-exp",
        "expired",
        "bad-sub",
        "bad-role",
    ],
)
def test_invalid_claims_are_translated_to_app_error(claims: dict[str, object]) -> None:
    settings = get_settings()
    token = jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(AppError) as raised:
        decode_access_token(token)

    assert raised.value.code == "invalid_token"
    assert raised.value.status_code == 401
