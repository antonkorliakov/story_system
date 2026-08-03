from sqlalchemy.exc import IntegrityError

from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.users.models import Role, User
from app.users.repository import UserRepository


class AuthService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def register(self, email: str, password: str) -> User:
        normalized_email = _normalize_email(email)
        if await self._users.get_by_email(normalized_email) is not None:
            raise _email_conflict()

        user = User(
            email=normalized_email,
            password_hash=hash_password(password),
            role=Role.CUSTOMER,
            is_active=True,
        )
        try:
            user = await self._users.create(user)
            await self._users.commit()
        except IntegrityError as error:
            raise _email_conflict() from error
        return user

    async def authenticate(self, email: str, password: str) -> User:
        user = await self._users.get_by_email(_normalize_email(email))
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise _invalid_credentials()
        return user


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _email_conflict() -> AppError:
    return AppError("email_conflict", "An account with this email already exists", 409)


def _invalid_credentials() -> AppError:
    return AppError("invalid_credentials", "Invalid email or password", 401)
