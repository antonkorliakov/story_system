import asyncio
import os
from collections.abc import Callable
from typing import Any, cast

from alembic.config import Config
from sqlalchemy import Numeric, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command


def _alembic_config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", os.environ["TEST_DATABASE_URL"])
    return config


def _schema_details[T](method: Callable[[Connection], T]) -> T:
    async def read_schema() -> T:
        engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(method)
        finally:
            await engine.dispose()

    return asyncio.run(read_schema())


def _columns(table_name: str) -> list[Any]:
    return _schema_details(lambda connection: inspect(connection).get_columns(table_name))


def _primary_key(table_name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _schema_details(lambda connection: inspect(connection).get_pk_constraint(table_name)),
    )


def _foreign_keys(table_name: str) -> list[Any]:
    return _schema_details(lambda connection: inspect(connection).get_foreign_keys(table_name))


def _indexes(table_name: str) -> list[Any]:
    return _schema_details(lambda connection: inspect(connection).get_indexes(table_name))


def _unique_constraints(table_name: str) -> list[Any]:
    return _schema_details(
        lambda connection: inspect(connection).get_unique_constraints(table_name)
    )


def _postgresql_enums() -> list[dict[str, Any]]:
    return cast(
        list[dict[str, Any]],
        _schema_details(lambda connection: cast(Any, inspect(connection)).get_enums()),
    )


def test_initial_migration_creates_and_reverses_the_application_schema() -> None:
    """Would fail if a migration omits a table, relationship, check, or listing index."""
    config = _alembic_config()

    try:
        command.downgrade(config, "base")
        command.upgrade(config, "head")

        table_names = _schema_details(lambda connection: inspect(connection).get_table_names())
        assert set(table_names) >= {
            "alembic_version",
            "users",
            "categories",
            "products",
            "carts",
            "cart_items",
            "orders",
            "order_items",
        }

        enums = _postgresql_enums()
        assert {enum["name"]: enum["labels"] for enum in enums} == {
            "role": ["customer", "admin"],
            "order_status": ["created"],
        }

        expected_columns = {
            "users": {
                "id",
                "email",
                "password_hash",
                "role",
                "is_active",
                "created_at",
                "updated_at",
            },
            "categories": {"id", "name", "slug", "created_at", "updated_at"},
            "products": {
                "id",
                "category_id",
                "name",
                "slug",
                "description",
                "price",
                "stock_quantity",
                "is_published",
                "created_at",
                "updated_at",
            },
            "carts": {"id", "user_id", "created_at", "updated_at"},
            "cart_items": {"id", "cart_id", "product_id", "quantity", "created_at", "updated_at"},
            "orders": {"id", "user_id", "status", "total", "created_at", "updated_at"},
            "order_items": {
                "id",
                "order_id",
                "product_id",
                "product_name",
                "unit_price",
                "quantity",
                "line_total",
                "created_at",
            },
        }
        for table_name, expected_names in expected_columns.items():
            columns = _columns(table_name)
            assert {column["name"] for column in columns} == expected_names
            assert all(column["nullable"] is False for column in columns)

            primary_key = _primary_key(table_name)
            assert primary_key["constrained_columns"] == ["id"]

        user_columns = {column["name"]: column for column in _columns("users")}
        order_columns = {column["name"]: column for column in _columns("orders")}
        product_columns = {column["name"]: column for column in _columns("products")}
        assert isinstance(user_columns["role"]["type"], postgresql.ENUM)
        assert user_columns["role"]["type"].name == "role"
        assert isinstance(order_columns["status"]["type"], postgresql.ENUM)
        assert order_columns["status"]["type"].name == "order_status"
        assert isinstance(product_columns["price"]["type"], Numeric)
        assert product_columns["price"]["type"].precision == 12
        assert product_columns["price"]["type"].scale == 2

        expected_foreign_keys: dict[str, set[tuple[tuple[str, ...], str, str]]] = {
            "products": {(("category_id",), "categories", "RESTRICT")},
            "carts": {(("user_id",), "users", "CASCADE")},
            "cart_items": {
                (("cart_id",), "carts", "CASCADE"),
                (("product_id",), "products", "RESTRICT"),
            },
            "orders": {(("user_id",), "users", "CASCADE")},
            "order_items": {
                (("order_id",), "orders", "CASCADE"),
                (("product_id",), "products", "RESTRICT"),
            },
        }
        for table_name, expected_keys in expected_foreign_keys.items():
            foreign_keys = _foreign_keys(table_name)
            assert {
                (
                    tuple(foreign_key["constrained_columns"]),
                    foreign_key["referred_table"],
                    foreign_key["options"].get("ondelete"),
                )
                for foreign_key in foreign_keys
            } == expected_keys

        product_checks = _schema_details(
            lambda connection: inspect(connection).get_check_constraints("products")
        )
        assert {check["name"] for check in product_checks} == {
            "ck_products_price_nonnegative",
            "ck_products_stock_quantity_nonnegative",
        }

        cart_item_checks = _schema_details(
            lambda connection: inspect(connection).get_check_constraints("cart_items")
        )
        assert {check["name"] for check in cart_item_checks} == {"ck_cart_items_quantity_positive"}

        order_item_checks = _schema_details(
            lambda connection: inspect(connection).get_check_constraints("order_items")
        )
        assert {check["name"] for check in order_item_checks} == {
            "ck_order_items_quantity_positive"
        }

        expected_indexes: dict[str, dict[str, bool]] = {
            "users": {"ix_users_email": True},
            "categories": {"ix_categories_slug": True},
            "products": {"ix_products_category_id": False, "ix_products_slug": True},
            "carts": {"ix_carts_user_id": False},
            "cart_items": {"ix_cart_items_cart_id": False, "ix_cart_items_product_id": False},
            "orders": {"ix_orders_user_id": False},
            "order_items": {"ix_order_items_order_id": False, "ix_order_items_product_id": False},
        }
        for table_name, expected_index_values in expected_indexes.items():
            indexes = _indexes(table_name)
            assert {index["name"]: index["unique"] for index in indexes} == expected_index_values

        expected_unique_constraints: dict[str, dict[str, tuple[str, ...]]] = {
            "users": {},
            "categories": {},
            "products": {},
            "carts": {"uq_carts_user_id": ("user_id",)},
            "cart_items": {"uq_cart_items_cart_product": ("cart_id", "product_id")},
        }
        for table_name, expected_constraint_values in expected_unique_constraints.items():
            unique_constraints = _unique_constraints(table_name)
            assert {
                constraint["name"]: tuple(constraint["column_names"])
                for constraint in unique_constraints
            } == expected_constraint_values
        command.downgrade(config, "base")

        table_names = _schema_details(lambda connection: inspect(connection).get_table_names())
        assert not {
            "users",
            "categories",
            "products",
            "carts",
            "cart_items",
            "orders",
            "order_items",
        } & set(table_names)

        enums = _postgresql_enums()
        assert not {"role", "order_status"} & {enum["name"] for enum in enums}
    finally:
        command.upgrade(config, "head")
