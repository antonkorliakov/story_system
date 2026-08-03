from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cart.models import Cart, CartItem


class CartRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user_id: UUID, *, for_update: bool = False) -> Cart:
        statement = select(Cart).where(Cart.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self._session.execute(statement)
        cart = result.scalar_one_or_none()
        if cart is not None:
            return cart

        cart = Cart(user_id=user_id)
        self._session.add(cart)
        try:
            await self._session.flush()
        except IntegrityError as error:
            await self._session.rollback()
            if getattr(error.orig, "sqlstate", None) != "23505":
                raise
            result = await self._session.execute(
                select(Cart).where(Cart.user_id == user_id).with_for_update()
            )
            return result.scalar_one()
        return cart

    async def get_item(self, cart_id: UUID, item_id: UUID) -> CartItem | None:
        result = await self._session.execute(
            select(CartItem)
            .where(CartItem.id == item_id, CartItem.cart_id == cart_id)
            .options(selectinload(CartItem.product))
        )
        return result.scalar_one_or_none()

    async def get_item_by_product(self, cart_id: UUID, product_id: UUID) -> CartItem | None:
        result = await self._session.execute(
            select(CartItem)
            .where(CartItem.cart_id == cart_id, CartItem.product_id == product_id)
            .options(selectinload(CartItem.product))
        )
        return result.scalar_one_or_none()

    async def create_item(self, item: CartItem) -> CartItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def delete_item(self, item: CartItem) -> None:
        await self._session.delete(item)

    async def list_items(self, cart_id: UUID) -> Sequence[CartItem]:
        result = await self._session.execute(
            select(CartItem)
            .where(CartItem.cart_id == cart_id)
            .order_by(CartItem.created_at, CartItem.id)
            .options(selectinload(CartItem.product))
        )
        return result.scalars().all()

    async def commit(self) -> None:
        await self._session.commit()
