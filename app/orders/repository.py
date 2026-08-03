from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.orders.models import Order


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, order: Order) -> Order:
        self._session.add(order)
        await self._session.flush()
        return order

    async def list_owned(
        self, user_id: UUID, limit: int, offset: int
    ) -> tuple[Sequence[Order], int]:
        items_result = await self._session.execute(
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
            .options(selectinload(Order.items))
        )
        total_result = await self._session.execute(
            select(func.count()).select_from(Order).where(Order.user_id == user_id)
        )
        return items_result.scalars().all(), total_result.scalar_one()

    async def get_owned(self, user_id: UUID, order_id: UUID) -> Order | None:
        result = await self._session.execute(
            select(Order)
            .where(Order.id == order_id, Order.user_id == user_id)
            .options(selectinload(Order.items))
        )
        return result.scalar_one_or_none()
