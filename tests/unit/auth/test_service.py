from typing import cast
from uuid import uuid4

import pytest

from app.auth.service import AuthService
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.users.models import Role, User
from app.users.repository import UserRepository


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self.users.get(email)

    async def create(self, user: User) -> User:
        self.users[user.email] = user
        return user

    async def commit(self) -> None:
        return None


async def test_register_normalizes_email_hashes_password_and_assigns_customer_role() -> None:
    repository = InMemoryUserRepository()
    service = AuthService(cast("UserRepository", repository))

    user = await service.register(" Customer@Example.com ", "correct horse battery staple")

    assert user.email == "customer@example.com"
    assert user.role is Role.CUSTOMER
    assert user.password_hash != "correct horse battery staple"
    assert verify_password("correct horse battery staple", user.password_hash)


async def test_register_rejects_a_normalized_duplicate_email() -> None:
    repository = InMemoryUserRepository()
    service = AuthService(cast("UserRepository", repository))
    await service.register("customer@example.com", "correct horse battery staple")

    with pytest.raises(AppError) as raised:
        await service.register(" Customer@Example.com ", "another correct password")

    assert raised.value.code == "email_conflict"
    assert raised.value.status_code == 409


@pytest.mark.parametrize(
    "email,password", [("missing@example.com", "password"), ("user@example.com", "wrong")]
)
async def test_authenticate_uses_generic_error_for_missing_and_bad_credentials(
    email: str, password: str
) -> None:
    repository = InMemoryUserRepository()
    repository.users["user@example.com"] = User(
        id=uuid4(),
        email="user@example.com",
        password_hash=hash_password("correct password"),
        role=Role.CUSTOMER,
        is_active=True,
    )
    service = AuthService(cast("UserRepository", repository))

    with pytest.raises(AppError) as raised:
        await service.authenticate(email, password)

    assert raised.value.code == "invalid_credentials"
    assert raised.value.status_code == 401


async def test_authenticate_rejects_an_inactive_user() -> None:
    repository = InMemoryUserRepository()
    user = User(
        id=uuid4(),
        email="inactive@example.com",
        password_hash=hash_password("correct password"),
        role=Role.CUSTOMER,
        is_active=False,
    )
    repository.users[user.email] = user
    service = AuthService(cast("UserRepository", repository))

    with pytest.raises(AppError) as raised:
        await service.authenticate("inactive@example.com", "password")

    assert raised.value.code == "invalid_credentials"
    assert raised.value.status_code == 401
