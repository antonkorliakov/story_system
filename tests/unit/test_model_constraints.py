from typing import cast

from sqlalchemy import CheckConstraint, Table

from app.cart.models import CartItem
from app.catalog.models import Product
from app.orders.models import OrderItem


def _check_names(table: Table) -> set[str]:
    return {
        str(constraint.name)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    }


def test_orm_metadata_matches_migration_check_constraints() -> None:
    assert _check_names(cast(Table, Product.__table__)) == {
        "ck_products_price_nonnegative",
        "ck_products_stock_quantity_nonnegative",
    }
    assert _check_names(cast(Table, CartItem.__table__)) == {"ck_cart_items_quantity_positive"}
    assert _check_names(cast(Table, OrderItem.__table__)) == {"ck_order_items_quantity_positive"}
