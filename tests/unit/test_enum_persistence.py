import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects import postgresql

from app.orders.models import Order, OrderStatus
from app.users.models import Role, User


def _initial_schema_migration() -> ModuleType:
    migration_path = (
        Path(__file__).parents[2] / "alembic" / "versions" / "20260727_0001_initial_schema.py"
    )
    specification = importlib.util.spec_from_file_location("initial_schema", migration_path)
    if specification is None or specification.loader is None:
        raise RuntimeError("Initial schema migration could not be loaded")

    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_role_enum_persists_lowercase_values_matching_the_migration() -> None:
    """Would fail if the ORM emits enum member names instead of PostgreSQL labels."""
    role_type = User.__table__.c.role.type
    assert isinstance(role_type, SqlEnum)
    processor = cast(
        Callable[[object], str] | None,
        role_type.bind_processor(postgresql.dialect()),  # type: ignore[no-untyped-call]
    )
    assert processor is not None

    assert role_type.enums == ["customer", "admin"]
    assert processor(Role.ADMIN) == "admin"
    assert _initial_schema_migration().role_enum.enums == ["customer", "admin"]


def test_order_status_enum_persists_lowercase_values_matching_the_migration() -> None:
    """Would fail if order writes use member names absent from the migration enum."""
    status_type = Order.__table__.c.status.type
    assert isinstance(status_type, SqlEnum)
    processor = cast(
        Callable[[object], str] | None,
        status_type.bind_processor(postgresql.dialect()),  # type: ignore[no-untyped-call]
    )
    assert processor is not None

    assert status_type.enums == ["created"]
    assert processor(OrderStatus.CREATED) == "created"
    assert _initial_schema_migration().order_status_enum.enums == ["created"]
