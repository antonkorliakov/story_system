from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.cart.models import CartItem
from app.cart.repository import CartRepository
from app.cart.schemas import CartItemCreate, CartItemResponse, CartItemUpdate, CartResponse
from app.cart.service import CartService
from app.catalog.repository import CatalogRepository
from app.core.database import get_db
from app.users.models import User

router = APIRouter(prefix="/api/v1/cart", tags=["cart"])


def _cart_service(db: AsyncSession) -> CartService:
    return CartService(CartRepository(db), CatalogRepository(db))


async def _cart_response(db: AsyncSession, user_id: UUID) -> CartResponse:
    cart = await _cart_service(db).get(user_id)
    responses = [_item_response(item) for item in cart.items]
    return CartResponse(
        items=responses, total=sum((item.line_total for item in responses), Decimal("0.00"))
    )


def _item_response(item: CartItem) -> CartItemResponse:
    return CartItemResponse(
        id=item.id,
        product_id=item.product_id,
        name=item.product.name,
        unit_price=item.product.price,
        quantity=item.quantity,
        line_total=item.product.price * item.quantity,
    )


@router.get("", response_model=CartResponse)
async def get_cart(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CartResponse:
    return await _cart_response(db, user.id)


@router.post("/items", response_model=CartItemResponse)
async def add_item(
    request: CartItemCreate,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CartItemResponse:
    item, created = await _cart_service(db).add_item(user.id, request.product_id, request.quantity)
    if created:
        response.status_code = status.HTTP_201_CREATED
    cart_items = await CartRepository(db).list_items(item.cart_id)
    return _item_response(next(cart_item for cart_item in cart_items if cart_item.id == item.id))


@router.patch("/items/{item_id}", response_model=CartItemResponse)
async def set_quantity(
    item_id: UUID,
    request: CartItemUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> CartItemResponse:
    item = await _cart_service(db).set_quantity(user.id, item_id, request.quantity)
    cart_items = await CartRepository(db).list_items(item.cart_id)
    return _item_response(next(cart_item for cart_item in cart_items if cart_item.id == item.id))


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_item(
    item_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    await _cart_service(db).remove_item(user.id, item_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
