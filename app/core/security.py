from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.core.errors import AppError

password_hash = PasswordHash.recommended()


@dataclass(frozen=True)
class TokenClaims:
    sub: UUID
    role: str
    iat: datetime
    exp: datetime


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_password: str) -> bool:
    return password_hash.verify(password, encoded_password)


def create_access_token(user_id: UUID, role: str) -> str:
    settings = get_settings()
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user_id), "role": role, "iat": issued_at, "exp": expires_at}
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        return TokenClaims(
            sub=UUID(payload["sub"]),
            role=_required_role(payload["role"]),
            iat=_timestamp_to_datetime(payload["iat"]),
            exp=_timestamp_to_datetime(payload["exp"]),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise AppError(
            "invalid_token",
            "Invalid or expired access token",
            401,
        ) from error


def _required_role(role: object) -> str:
    if not isinstance(role, str):
        raise TypeError("Token role must be a string")
    return role


def _timestamp_to_datetime(timestamp: object) -> datetime:
    if not isinstance(timestamp, int | float):
        raise TypeError("Token timestamps must be numeric")
    return datetime.fromtimestamp(timestamp, UTC)
