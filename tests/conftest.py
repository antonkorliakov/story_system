import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import create_app
from app.users.models import Role, User


def _get_test_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        raise pytest.UsageError("TEST_DATABASE_URL must be set")

    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "postgresql" or parsed_url.get_driver_name() != "asyncpg":
        raise pytest.UsageError("TEST_DATABASE_URL must use the PostgreSQL asyncpg backend")

    database_name = parsed_url.database
    if database_name is None or not database_name.endswith("_test"):
        raise pytest.UsageError("TEST_DATABASE_URL must name a database ending in _test")

    return database_url


test_engine = create_async_engine(_get_test_database_url(), pool_pre_ping=True)
test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(scope="session")
async def database_schema() -> AsyncIterator[None]:
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest.fixture
async def db_session(database_schema: None) -> AsyncIterator[AsyncSession]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = test_session_factory(bind=connection)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.fixture
async def admin_headers(db_session: AsyncSession) -> AsyncIterator[dict[str, str]]:
    admin = User(
        id=uuid4(),
        email="admin@example.com",
        password_hash=hash_password("correct horse battery staple"),
        role=Role.ADMIN,
        is_active=True,
    )
    db_session.add(admin)
    await db_session.flush()
    yield {"Authorization": f"Bearer {create_access_token(admin.id, admin.role.value)}"}


@pytest.fixture
async def customer_headers(db_session: AsyncSession) -> AsyncIterator[dict[str, str]]:
    customer = User(
        id=uuid4(),
        email="customer@example.com",
        password_hash=hash_password("correct horse battery staple"),
        role=Role.CUSTOMER,
        is_active=True,
    )
    db_session.add(customer)
    await db_session.flush()
    yield {"Authorization": f"Bearer {create_access_token(customer.id, customer.role.value)}"}
