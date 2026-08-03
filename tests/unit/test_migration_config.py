from alembic.config import Config
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.core.migrations import configure_database_url


def test_database_url_environment_overrides_alembic_ini_without_connecting(
    monkeypatch: MonkeyPatch,
) -> None:
    config = Config("alembic.ini")
    ini_url = config.get_main_option("sqlalchemy.url")
    database_url = "postgresql+asyncpg://compose:password@db:5432/compose_database"

    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    try:
        assert configure_database_url(config) == database_url
        assert config.get_main_option("sqlalchemy.url") == database_url
        assert config.get_main_option("sqlalchemy.url") != ini_url
    finally:
        get_settings.cache_clear()


def test_absent_database_url_preserves_caller_supplied_alembic_url(
    monkeypatch: MonkeyPatch,
) -> None:
    config = Config("alembic.ini")
    test_database_url = "postgresql+asyncpg://shop:shop@localhost:5432/shop_test"
    config.set_main_option("sqlalchemy.url", test_database_url)

    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        assert configure_database_url(config) == test_database_url
        assert config.get_main_option("sqlalchemy.url") == test_database_url
    finally:
        get_settings.cache_clear()


def test_explicit_test_url_wins_over_ambient_non_test_database_url(
    monkeypatch: MonkeyPatch,
) -> None:
    config = Config("alembic.ini")
    test_database_url = "postgresql+asyncpg://shop:shop@localhost:5432/shop_test"
    config.set_main_option("sqlalchemy.url", test_database_url)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://production:secret@production-db:5432/shop",
    )

    assert configure_database_url(config) == test_database_url
    assert config.get_main_option("sqlalchemy.url") == test_database_url
