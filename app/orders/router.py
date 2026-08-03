from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.cart.repository import CartRepository
from app.catalog.repository import CatalogRepository
from app.core.database import get_db
from app.core.errors import AppError
from app.orders.models import Order
from app.orders.repository import OrderRepository
from app.orders.schemas import OrderListResponse, OrderResponse
from app.orders.service import OrderService
from app.users.models import User

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _order_service(db: AsyncSession) -> OrderService:
    return OrderService(
        db,
        CartRepository(db),
        CatalogRepository(db),
        OrderRepository(db),
    )


@router.post("/checkout", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Order:
    return await _order_service(db).checkout(user.id)


@router.get("", response_model=OrderListResponse)
async def list_orders(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderListResponse:
    items, total = await OrderRepository(db).list_owned(user.id, limit, offset)
    return OrderListResponse(items=list(items), limit=limit, offset=offset, total=total)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Order:
    order = await OrderRepository(db).get_owned(user.id, order_id)
    if order is None:
        raise AppError("order_not_found", "Order not found", 404)
    return order
