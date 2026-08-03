from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.repository import CartRepository


class EmptyResult:
    def scalar_one_or_none(self) -> None:
        return None


class FailingFlushSession:
    def __init__(self, sqlstate: str) -> None:
        self._sqlstate = sqlstate
        self.rollback_count = 0

    async def execute(self, statement: object) -> EmptyResult:
        return EmptyResult()

    def add(self, instance: object) -> None:
        return None

    async def flush(self) -> None:
        original = type("DatabaseError", (), {"sqlstate": self._sqlstate})()
        raise IntegrityError("statement", {}, original)

    async def rollback(self) -> None:
        self.rollback_count += 1


async def test_cart_creation_does_not_treat_non_unique_integrity_error_as_a_race() -> None:
    session = FailingFlushSession("23503")
    repository = CartRepository(cast("AsyncSession", session))

    with pytest.raises(IntegrityError):
        await repository.get_or_create(uuid4())

    assert session.rollback_count == 1
