import pytest
from conftest import _get_test_database_url  # type: ignore[import-not-found]


def test_test_database_url_rejects_non_postgresql_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///shop_test")

    with pytest.raises(pytest.UsageError, match="PostgreSQL"):
        _get_test_database_url()


def test_test_database_url_accepts_asyncpg_postgresql_test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = "postgresql+asyncpg://shop:shop@localhost:5432/shop_test"
    monkeypatch.setenv("TEST_DATABASE_URL", database_url)

    assert _get_test_database_url() == database_url
