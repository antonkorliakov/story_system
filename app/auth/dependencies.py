from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.users.models import Role, User
from app.users.repository import UserRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if token is None:
        raise AppError("invalid_token", "Invalid or expired access token", 401)
    claims = decode_access_token(token)
    user = await UserRepository(db).get_by_id(claims.sub)
    if user is None or not user.is_active:
        raise AppError("invalid_token", "Invalid or expired access token", 401)
    return user


async def require_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if user.role is not Role.ADMIN:
        raise AppError("forbidden", "Administrator access required", 403)
    return user
