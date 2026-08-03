from uuid import UUID

from sqlalchemy.orm.attributes import set_committed_value

from app.cart.models import Cart, CartItem
from app.cart.repository import CartRepository
from app.catalog.models import Product
from app.catalog.repository import CatalogRepository
from app.core.errors import AppError


class CartService:
    def __init__(self, carts: CartRepository, catalog: CatalogRepository) -> None:
        self._carts = carts
        self._catalog = catalog

    async def get(self, user_id: UUID) -> Cart:
        cart = await self._carts.get_or_create(user_id)
        items = list(await self._carts.list_items(cart.id))
        for item in items:
            item.product = await self._require_published_product(item.product_id)
        set_committed_value(cart, "items", items)
        await self._carts.commit()
        return cart

    async def add_item(
        self, user_id: UUID, product_id: UUID, quantity: int
    ) -> tuple[CartItem, bool]:
        _require_positive_quantity(quantity)
        cart = await self._carts.get_or_create(user_id, for_update=True)
        product = await self._require_published_product(product_id)
        item = await self._carts.get_item_by_product(cart.id, product_id)
        aggregate_quantity = quantity if item is None else item.quantity + quantity
        _require_available_stock(aggregate_quantity, product.stock_quantity)
        if item is None:
            item = await self._carts.create_item(
                CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity)
            )
            created = True
        else:
            item.quantity = aggregate_quantity
            created = False
        await self._carts.commit()
        return item, created

    async def set_quantity(self, user_id: UUID, item_id: UUID, quantity: int) -> CartItem:
        _require_positive_quantity(quantity)
        cart = await self._carts.get_or_create(user_id, for_update=True)
        item = await self._require_item(cart, item_id)
        product = await self._require_published_product(item.product_id)
        _require_available_stock(quantity, product.stock_quantity)
        item.quantity = quantity
        await self._carts.commit()
        return item

    async def remove_item(self, user_id: UUID, item_id: UUID) -> None:
        cart = await self._carts.get_or_create(user_id, for_update=True)
        item = await self._require_item(cart, item_id)
        await self._carts.delete_item(item)
        await self._carts.commit()

    async def _require_published_product(self, product_id: UUID) -> Product:
        product = await self._catalog.get_published_product(product_id)
        if product is None:
            raise AppError("product_not_found", "Product not found", 404)
        return product

    async def _require_item(self, cart: Cart, item_id: UUID) -> CartItem:
        item = await self._carts.get_item(cart.id, item_id)
        if item is None:
            raise AppError("cart_item_not_found", "Cart item not found", 404)
        return item


def _require_positive_quantity(quantity: int) -> None:
    if quantity < 1:
        raise AppError("invalid_quantity", "Quantity must be positive", 422)


def _require_available_stock(quantity: int, stock_quantity: int) -> None:
    if quantity > stock_quantity:
        raise AppError("insufficient_stock", "Insufficient stock", 409)
