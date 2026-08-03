import asyncio
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from conftest import (  # type: ignore[import-not-found]
    test_session_factory as _test_session_factory,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.models import Cart, CartItem
from app.cart.repository import CartRepository
from app.catalog.models import Category, Product
from app.catalog.repository import CatalogRepository
from app.core.errors import AppError
from app.orders.models import Order
from app.orders.repository import OrderRepository
from app.orders.service import OrderService
from app.users.models import Role, User


async def _checkout_service(session: AsyncSession) -> OrderService:
    return OrderService(
        session,
        CartRepository(session),
        CatalogRepository(session),
        OrderRepository(session),
    )


async def test_checkout_creates_immutable_snapshot_decrements_stock_and_clears_cart(
    db_session: AsyncSession,
) -> None:
    user, product, cart = await _checkout_fixture(db_session, quantity=2, stock_quantity=2)

    order = await (await _checkout_service(db_session)).checkout(user.id)
    product.name = "Renamed"
    product.price = Decimal("1.00")
    await db_session.flush()

    loaded = await OrderRepository(db_session).get_owned(user.id, order.id)
    assert loaded is not None
    assert loaded.status.value == "created"
    assert loaded.total == Decimal("999.80")
    assert [(item.product_name, item.unit_price, item.line_total) for item in loaded.items] == [
        ("Phone", Decimal("499.90"), Decimal("999.80"))
    ]
    await db_session.refresh(product)
    assert product.stock_quantity == 0
    assert await CartRepository(db_session).list_items(cart.id) == []


async def test_checkout_rolls_back_flushed_order_stock_and_cart_changes(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, product, cart = await _checkout_fixture(db_session, quantity=1, stock_quantity=1)
    original_delete_item = CartRepository.delete_item
    changes_flushed = False

    async def fail_after_flushed_deletion(repository: CartRepository, item: CartItem) -> None:
        nonlocal changes_flushed
        await original_delete_item(repository, item)
        await repository._session.flush()
        changes_flushed = True
        raise RuntimeError(f"failure after flushing deletion {item.id}")

    monkeypatch.setattr(CartRepository, "delete_item", fail_after_flushed_deletion)

    with pytest.raises(RuntimeError, match="failure after flushing deletion"):
        await (await _checkout_service(db_session)).checkout(user.id)

    assert changes_flushed is True
    await db_session.refresh(product)
    assert product.stock_quantity == 1
    assert len(await CartRepository(db_session).list_items(cart.id)) == 1
    assert (
        await db_session.scalar(
            select(func.count()).select_from(Order).where(Order.user_id == user.id)
        )
        == 0
    )


async def test_concurrent_checkouts_cannot_sell_the_final_unit(
    database_schema: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suffix = uuid4().hex
    user_ids: list[UUID] = []
    category_id: UUID | None = None
    product_id: UUID | None = None
    async with _test_session_factory() as setup:
        first = User(email=f"first-{suffix}@example.com", password_hash="hash", role=Role.CUSTOMER)
        second = User(
            email=f"second-{suffix}@example.com", password_hash="hash", role=Role.CUSTOMER
        )
        category = Category(name="Concurrency", slug=f"concurrency-{suffix}")
        setup.add_all([first, second, category])
        await setup.flush()
        product = Product(
            category_id=category.id,
            name="Final unit",
            slug=f"final-unit-{suffix}",
            description="",
            price=Decimal("9.99"),
            stock_quantity=1,
            is_published=True,
        )
        setup.add(product)
        await setup.flush()
        carts = [Cart(user_id=first.id), Cart(user_id=second.id)]
        setup.add_all(carts)
        await setup.flush()
        setup.add_all(
            [
                CartItem(cart_id=carts[0].id, product_id=product.id, quantity=1),
                CartItem(cart_id=carts[1].id, product_id=product.id, quantity=1),
            ]
        )
        await setup.commit()
        user_ids = [first.id, second.id]
        category_id = category.id
        product_id = product.id

    original_lock_products = CatalogRepository.lock_products
    preloaded_sessions = 0
    both_sessions_preloaded = asyncio.Event()

    async def lock_after_both_sessions_preload(
        repository: CatalogRepository, product_ids: list[UUID]
    ) -> list[Product]:
        nonlocal preloaded_sessions
        preloaded_sessions += 1
        if preloaded_sessions == 2:
            both_sessions_preloaded.set()
        await both_sessions_preloaded.wait()
        return await original_lock_products(repository, product_ids)

    monkeypatch.setattr(CatalogRepository, "lock_products", lock_after_both_sessions_preload)

    async def checkout(user_id: UUID) -> Order:
        async with _test_session_factory() as session:
            return await (await _checkout_service(session)).checkout(user_id)

    try:
        results = await asyncio.gather(
            *(checkout(user_id) for user_id in user_ids), return_exceptions=True
        )
        orders = [result for result in results if isinstance(result, Order)]
        errors = [result for result in results if isinstance(result, AppError)]

        assert preloaded_sessions == 2
        assert len(orders) == 1
        assert len(orders) + len(errors) == len(results)
        assert [(error.code, error.status_code) for error in errors] == [
            ("insufficient_stock", 409)
        ]
        async with _test_session_factory() as verification:
            assert (
                await verification.scalar(
                    select(Product.stock_quantity).where(Product.id == product_id)
                )
                == 0
            )
            assert (
                await verification.scalar(
                    select(func.count()).select_from(Order).where(Order.user_id.in_(user_ids))
                )
                == 1
            )
    finally:
        async with _test_session_factory() as cleanup:
            await cleanup.execute(delete(User).where(User.id.in_(user_ids)))
            if product_id is not None:
                await cleanup.execute(delete(Product).where(Product.id == product_id))
            if category_id is not None:
                await cleanup.execute(delete(Category).where(Category.id == category_id))
            await cleanup.commit()


async def _checkout_fixture(
    session: AsyncSession, *, quantity: int, stock_quantity: int
) -> tuple[User, Product, Cart]:
    suffix = uuid4().hex
    user = User(email=f"checkout-{suffix}@example.com", password_hash="hash", role=Role.CUSTOMER)
    category = Category(name="Phones", slug=f"phones-{suffix}")
    session.add_all([user, category])
    await session.flush()
    product = Product(
        category_id=category.id,
        name="Phone",
        slug=f"phone-{suffix}",
        description="",
        price=Decimal("499.90"),
        stock_quantity=stock_quantity,
        is_published=True,
    )
    cart = Cart(user_id=user.id)
    session.add_all([product, cart])
    await session.flush()
    session.add(CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity))
    await session.flush()
    return user, product, cart
