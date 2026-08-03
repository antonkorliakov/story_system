from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.cart.repository import CartRepository
from app.catalog.repository import CatalogRepository
from app.core.errors import AppError
from app.orders.models import Order, OrderItem, OrderStatus
from app.orders.repository import OrderRepository

CENT = Decimal("0.01")


class OrderService:
    def __init__(
        self,
        session: AsyncSession,
        carts: CartRepository,
        catalog: CatalogRepository,
        orders: OrderRepository,
    ) -> None:
        self._session = session
        self._carts = carts
        self._catalog = catalog
        self._orders = orders

    async def checkout(self, user_id: UUID) -> Order:
        async with self._session.begin_nested():
            cart = await self._carts.get_or_create(user_id, for_update=True)
            cart_items = list(await self._carts.list_items(cart.id))
            if not cart_items:
                raise AppError("empty_cart", "Cart is empty", 400)

            product_ids = sorted(item.product_id for item in cart_items)
            products = await self._catalog.lock_products(product_ids)
            products_by_id = {product.id: product for product in products}

            order_items: list[OrderItem] = []
            for cart_item in cart_items:
                product = products_by_id.get(cart_item.product_id)
                if product is None or not product.is_published:
                    raise AppError("product_unavailable", "Product is unavailable", 409)
                if product.stock_quantity < cart_item.quantity:
                    raise AppError("insufficient_stock", "Insufficient stock", 409)
                line_total = (product.price * cart_item.quantity).quantize(CENT)
                order_items.append(
                    OrderItem(
                        product_id=product.id,
                        product_name=product.name,
                        unit_price=product.price,
                        quantity=cart_item.quantity,
                        line_total=line_total,
                    )
                )

            order = Order(
                user_id=user_id,
                status=OrderStatus.CREATED,
                total=sum((item.line_total for item in order_items), Decimal("0.00")),
                items=order_items,
            )
            await self._orders.create(order)

            for cart_item in cart_items:
                products_by_id[cart_item.product_id].stock_quantity -= cart_item.quantity
                await self._carts.delete_item(cart_item)

        await self._session.commit()
        return order
