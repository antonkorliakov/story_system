from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.catalog.models import Category, Product
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import ProductCreate
from app.catalog.service import CatalogService
from app.core.errors import AppError


class InMemoryCatalogRepository:
    def __init__(self) -> None:
        self.categories: dict[object, Category] = {}
        self.products: dict[object, Product] = {}

    async def get_category(self, category_id: object) -> Category | None:
        return self.categories.get(category_id)

    async def get_category_by_slug(self, slug: str) -> Category | None:
        return next(
            (category for category in self.categories.values() if category.slug == slug), None
        )

    async def create_category(self, category: Category) -> Category:
        self.categories[category.id] = category
        return category

    async def delete_category(self, category: Category) -> None:
        del self.categories[category.id]

    async def category_has_products(self, category_id: object) -> bool:
        return any(product.category_id == category_id for product in self.products.values())

    async def get_product(self, product_id: object) -> Product | None:
        return self.products.get(product_id)

    async def get_product_by_slug(self, slug: str) -> Product | None:
        return next((product for product in self.products.values() if product.slug == slug), None)

    async def create_product(self, product: Product) -> Product:
        self.products[product.id] = product
        return product

    async def commit(self) -> None:
        return None


class FailingCommitCatalogRepository(InMemoryCatalogRepository):
    def __init__(self, sqlstate: str) -> None:
        super().__init__()
        self._sqlstate = sqlstate

    async def commit(self) -> None:
        original = type("DatabaseError", (), {"sqlstate": self._sqlstate})()
        raise IntegrityError("statement", {}, original)


def _category(slug: str = "phones") -> Category:
    timestamp = datetime.now(UTC)
    return Category(
        id=uuid4(), name="Phones", slug=slug, created_at=timestamp, updated_at=timestamp
    )


async def test_create_product_rejects_a_missing_category() -> None:
    service = CatalogService(cast("CatalogRepository", InMemoryCatalogRepository()))

    with pytest.raises(AppError) as raised:
        await service.create_product(
            category_id=uuid4(),
            name="Phone",
            slug="phone",
            description="",
            price=Decimal("499.90"),
            stock_quantity=3,
            is_published=True,
        )

    assert raised.value.code == "category_not_found"
    assert raised.value.status_code == 404


async def test_create_category_rejects_an_existing_slug() -> None:
    repository = InMemoryCatalogRepository()
    existing = _category()
    repository.categories[existing.id] = existing
    service = CatalogService(cast("CatalogRepository", repository))

    with pytest.raises(AppError) as raised:
        await service.create_category("New phones", "phones")

    assert raised.value.code == "category_slug_conflict"
    assert raised.value.status_code == 409


async def test_unique_integrity_error_is_translated_to_slug_conflict() -> None:
    repository = FailingCommitCatalogRepository("23505")
    service = CatalogService(cast("CatalogRepository", repository))

    with pytest.raises(AppError) as raised:
        await service.create_category("Phones", "phones")

    assert raised.value.code == "category_slug_conflict"


async def test_non_unique_integrity_error_is_not_misreported_as_slug_conflict() -> None:
    repository = FailingCommitCatalogRepository("23514")
    service = CatalogService(cast("CatalogRepository", repository))

    with pytest.raises(IntegrityError):
        await service.create_category("Phones", "phones")


async def test_unpublish_product_hides_the_existing_product() -> None:
    repository = InMemoryCatalogRepository()
    category = _category()
    repository.categories[category.id] = category
    product = Product(
        id=uuid4(),
        category_id=category.id,
        name="Phone",
        slug="phone",
        description="",
        price=Decimal("499.90"),
        stock_quantity=3,
        is_published=True,
    )
    repository.products[product.id] = product
    service = CatalogService(cast("CatalogRepository", repository))

    unpublished = await service.unpublish_product(product.id)

    assert unpublished.is_published is False


async def test_delete_category_rejects_a_category_with_unpublished_products() -> None:
    repository = InMemoryCatalogRepository()
    category = _category()
    repository.categories[category.id] = category
    repository.products[uuid4()] = Product(
        id=uuid4(),
        category_id=category.id,
        name="Draft",
        slug="draft",
        description="",
        price=Decimal("10.00"),
        stock_quantity=1,
        is_published=False,
    )
    service = CatalogService(cast("CatalogRepository", repository))

    with pytest.raises(AppError) as raised:
        await service.delete_category(category.id)

    assert raised.value.code == "category_not_empty"
    assert raised.value.status_code == 409


@pytest.mark.parametrize(
    "payload",
    [
        {"price": "-0.01", "stock_quantity": 1},
        {"price": "10.001", "stock_quantity": 1},
        {"price": "10.00", "stock_quantity": -1},
    ],
)
def test_product_create_rejects_invalid_money_or_stock(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProductCreate.model_validate(
            {
                "category_id": str(uuid4()),
                "name": "Phone",
                "slug": "phone",
                "description": "",
                "is_published": True,
                **payload,
            }
        )
