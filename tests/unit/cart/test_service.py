from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.cart.models import Cart, CartItem
from app.cart.repository import CartRepository
from app.cart.service import CartService
from app.catalog.models import Product
from app.catalog.repository import CatalogRepository
from app.core.errors import AppError


class InMemoryCartRepository:
    def __init__(self) -> None:
        self.carts: dict[UUID, Cart] = {}
        self.items: dict[UUID, CartItem] = {}

    async def get_or_create(self, user_id: UUID, *, for_update: bool = False) -> Cart:
        cart = self.carts.get(user_id)
        if cart is None:
            cart = Cart(id=uuid4(), user_id=user_id)
            self.carts[user_id] = cart
        return cart

    async def get_item(self, cart_id: UUID, item_id: UUID) -> CartItem | None:
        item = self.items.get(item_id)
        return item if item is not None and item.cart_id == cart_id else None

    async def get_item_by_product(self, cart_id: UUID, product_id: UUID) -> CartItem | None:
        return next(
            (
                item
                for item in self.items.values()
                if item.cart_id == cart_id and item.product_id == product_id
            ),
            None,
        )

    async def create_item(self, item: CartItem) -> CartItem:
        self.items[item.id] = item
        return item

    async def delete_item(self, item: CartItem) -> None:
        del self.items[item.id]

    async def list_items(self, cart_id: UUID) -> list[CartItem]:
        return [item for item in self.items.values() if item.cart_id == cart_id]

    async def commit(self) -> None:
        return None


class InMemoryCatalogRepository:
    def __init__(self, products: list[Product]) -> None:
        self.products = {product.id: product for product in products}

    async def get_published_product(self, product_id: UUID) -> Product | None:
        product = self.products.get(product_id)
        return product if product is not None and product.is_published else None


def _product(*, stock_quantity: int = 3, is_published: bool = True) -> Product:
    timestamp = datetime.now(UTC)
    return Product(
        id=uuid4(),
        category_id=uuid4(),
        name="Phone",
        slug="phone",
        description="",
        price=Decimal("499.90"),
        stock_quantity=stock_quantity,
        is_published=is_published,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _service(cart: InMemoryCartRepository, catalog: InMemoryCatalogRepository) -> CartService:
    return CartService(cast("CartRepository", cart), cast("CatalogRepository", catalog))


async def test_add_same_product_increments_its_existing_quantity() -> None:
    carts = InMemoryCartRepository()
    product = _product()
    service = _service(carts, InMemoryCatalogRepository([product]))
    user_id = uuid4()

    created, was_new = await service.add_item(user_id, product.id, 1)
    incremented, was_incremented_new = await service.add_item(user_id, product.id, 1)

    assert was_new is True
    assert was_incremented_new is False
    assert created.id == incremented.id
    assert incremented.quantity == 2


async def test_add_item_rejects_a_requested_aggregate_quantity_above_stock() -> None:
    carts = InMemoryCartRepository()
    product = _product(stock_quantity=2)
    service = _service(carts, InMemoryCatalogRepository([product]))
    user_id = uuid4()
    await service.add_item(user_id, product.id, 2)

    with pytest.raises(AppError) as raised:
        await service.add_item(user_id, product.id, 1)

    assert raised.value.code == "insufficient_stock"
    assert raised.value.status_code == 409


async def test_set_quantity_cannot_access_an_item_from_another_users_cart() -> None:
    carts = InMemoryCartRepository()
    product = _product()
    service = _service(carts, InMemoryCatalogRepository([product]))
    owner_id = uuid4()
    item, _ = await service.add_item(owner_id, product.id, 1)

    with pytest.raises(AppError) as raised:
        await service.set_quantity(uuid4(), item.id, 2)

    assert raised.value.code == "cart_item_not_found"
    assert raised.value.status_code == 404


async def test_add_item_hides_unpublished_products() -> None:
    carts = InMemoryCartRepository()
    product = _product(is_published=False)
    service = _service(carts, InMemoryCatalogRepository([product]))

    with pytest.raises(AppError) as raised:
        await service.add_item(uuid4(), product.id, 1)

    assert raised.value.code == "product_not_found"
    assert raised.value.status_code == 404


async def test_get_hides_items_when_their_product_is_subsequently_unpublished() -> None:
    carts = InMemoryCartRepository()
    product = _product()
    catalog = InMemoryCatalogRepository([product])
    service = _service(carts, catalog)
    user_id = uuid4()
    await service.add_item(user_id, product.id, 1)
    product.is_published = False

    with pytest.raises(AppError) as raised:
        await service.get(user_id)

    assert raised.value.code == "product_not_found"
    assert raised.value.status_code == 404
