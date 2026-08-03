from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.models import Cart, CartItem
from app.cart.repository import CartRepository
from app.catalog.models import Product
from app.catalog.repository import CatalogRepository
from app.core.errors import AppError
from app.orders.models import Order
from app.orders.repository import OrderRepository
from app.orders.service import OrderService


class NestedTransaction(AbstractAsyncContextManager[None]):
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


class InMemorySession:
    def __init__(self) -> None:
        self.nested_transactions = 0
        self.commits = 0

    def begin_nested(self) -> NestedTransaction:
        self.nested_transactions += 1
        return NestedTransaction()

    async def commit(self) -> None:
        self.commits += 1


class InMemoryCartRepository:
    def __init__(self, user_id: UUID, items: list[CartItem]) -> None:
        self.cart = Cart(id=uuid4(), user_id=user_id)
        self.items = items
        for item in items:
            item.cart_id = self.cart.id
        self.lock_requested = False

    async def get_or_create(self, user_id: UUID, *, for_update: bool = False) -> Cart:
        assert user_id == self.cart.user_id
        self.lock_requested = for_update
        return self.cart

    async def list_items(self, cart_id: UUID) -> list[CartItem]:
        assert cart_id == self.cart.id
        return list(self.items)

    async def delete_item(self, item: CartItem) -> None:
        self.items.remove(item)


class InMemoryCatalogRepository:
    def __init__(self, products: list[Product]) -> None:
        self.products = products
        self.locked_product_ids: list[UUID] = []

    async def lock_products(self, product_ids: list[UUID]) -> list[Product]:
        self.locked_product_ids = product_ids
        return list(reversed(self.products))


class InMemoryOrderRepository:
    def __init__(self) -> None:
        self.orders: list[Order] = []

    async def create(self, order: Order) -> Order:
        self.orders.append(order)
        return order


def _product(
    *,
    product_id: UUID | None = None,
    price: Decimal = Decimal("19.99"),
    stock_quantity: int = 5,
    is_published: bool = True,
) -> Product:
    timestamp = datetime.now(UTC)
    return Product(
        id=product_id or uuid4(),
        category_id=uuid4(),
        name="Phone",
        slug=f"phone-{uuid4()}",
        description="",
        price=price,
        stock_quantity=stock_quantity,
        is_published=is_published,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _item(product_id: UUID, quantity: int) -> CartItem:
    timestamp = datetime.now(UTC)
    return CartItem(
        id=uuid4(),
        cart_id=uuid4(),
        product_id=product_id,
        quantity=quantity,
        created_at=timestamp,
        updated_at=timestamp,
    )


def _service(
    session: InMemorySession,
    carts: InMemoryCartRepository,
    catalog: InMemoryCatalogRepository,
    orders: InMemoryOrderRepository,
) -> OrderService:
    return OrderService(
        cast("AsyncSession", session),
        cast("CartRepository", carts),
        cast("CatalogRepository", catalog),
        cast("OrderRepository", orders),
    )


async def test_checkout_snapshots_totals_decrements_stock_and_clears_cart() -> None:
    user_id = uuid4()
    first = _product(price=Decimal("3.333"), stock_quantity=4)
    second = _product(price=Decimal("5.50"), stock_quantity=3)
    carts = InMemoryCartRepository(user_id, [_item(first.id, 3), _item(second.id, 2)])
    catalog = InMemoryCatalogRepository([first, second])
    orders = InMemoryOrderRepository()
    session = InMemorySession()

    order = await _service(session, carts, catalog, orders).checkout(user_id)

    assert carts.lock_requested is True
    assert catalog.locked_product_ids == sorted([first.id, second.id])
    assert [
        (item.product_id, item.unit_price, item.quantity, item.line_total) for item in order.items
    ] == [
        (first.id, Decimal("3.333"), 3, Decimal("10.00")),
        (second.id, Decimal("5.50"), 2, Decimal("11.00")),
    ]
    assert order.total == Decimal("21.00")
    assert first.stock_quantity == 1
    assert second.stock_quantity == 1
    assert carts.items == []
    assert orders.orders == [order]
    assert session.nested_transactions == 1
    assert session.commits == 1


@pytest.mark.parametrize(
    ("products", "quantity", "expected_code"),
    [
        ([], 1, "product_unavailable"),
        ([_product(is_published=False)], 1, "product_unavailable"),
        ([_product(stock_quantity=1)], 2, "insufficient_stock"),
    ],
)
async def test_checkout_rejects_unavailable_or_insufficient_products_without_committing(
    products: list[Product], quantity: int, expected_code: str
) -> None:
    user_id = uuid4()
    product_id = products[0].id if products else uuid4()
    carts = InMemoryCartRepository(user_id, [_item(product_id, quantity)])
    orders = InMemoryOrderRepository()
    session = InMemorySession()

    with pytest.raises(AppError) as raised:
        await _service(session, carts, InMemoryCatalogRepository(products), orders).checkout(
            user_id
        )

    assert raised.value.code == expected_code
    assert raised.value.status_code == 409
    assert carts.items != []
    assert orders.orders == []
    assert session.commits == 0


async def test_checkout_rejects_an_empty_cart_without_locking_products_or_committing() -> None:
    user_id = uuid4()
    carts = InMemoryCartRepository(user_id, [])
    catalog = InMemoryCatalogRepository([])
    orders = InMemoryOrderRepository()
    session = InMemorySession()

    with pytest.raises(AppError) as raised:
        await _service(session, carts, catalog, orders).checkout(user_id)

    assert raised.value.code == "empty_cart"
    assert raised.value.status_code == 400
    assert catalog.locked_product_ids == []
    assert orders.orders == []
    assert session.commits == 0
