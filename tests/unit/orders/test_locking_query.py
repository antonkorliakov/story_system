from typing import cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.base import Executable

from app.catalog.models import Product
from app.catalog.repository import CatalogRepository


class EmptyScalarResult:
    def all(self) -> list[Product]:
        return []


class EmptyResult:
    def scalars(self) -> EmptyScalarResult:
        return EmptyScalarResult()


class RecordingSession:
    def __init__(self) -> None:
        self.statement: Executable | None = None

    async def execute(self, statement: Executable) -> EmptyResult:
        self.statement = statement
        return EmptyResult()


async def test_product_lock_query_refreshes_preloaded_products() -> None:
    session = RecordingSession()

    await CatalogRepository(cast("AsyncSession", session)).lock_products([uuid4()])

    assert session.statement is not None
    assert session.statement.get_execution_options()["populate_existing"] is True
