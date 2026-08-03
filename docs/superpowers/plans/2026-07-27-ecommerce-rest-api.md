# Ecommerce REST API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-shaped FastAPI/PostgreSQL MVP where customers authenticate, browse a catalog, manage a cart, and atomically checkout while administrators manage categories and products.

**Architecture:** Implement one asynchronous FastAPI deployment split into focused `auth`, `users`, `catalog`, `cart`, and `orders` packages. Routers own HTTP translation, services own business rules and transactions, and repositories own SQLAlchemy queries; PostgreSQL is the authority for uniqueness, ownership, money, and concurrent stock updates.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2 async, asyncpg, Alembic, PostgreSQL 16, PyJWT, pwdlib/Argon2, Typer, pytest, pytest-asyncio, HTTPX, Ruff, mypy, Docker Compose, GitHub Actions.

## Global Constraints

- Every API path is prefixed with `/api/v1`.
- Public registration always creates `customer`; only the CLI may create or promote an `admin`.
- Access JWT lifetime defaults to 30 minutes; refresh tokens are outside MVP.
- Money uses `Decimal` and PostgreSQL `numeric(12, 2)`, never binary floating point.
- A customer has at most one active cart and can read only their own cart and orders.
- Product deletion is soft deletion by setting `is_published=false`; categories with products cannot be deleted.
- Checkout locks product rows in stable ID order, revalidates publication and stock, creates immutable item snapshots, decrements stock, and clears the cart in one transaction.
- Order status is `created`; payment, delivery, cancellation, returns, promotions, reviews, and stock restoration are outside MVP.
- Errors use `{"error":{"code":"...","message":"...","details":{...}}}`.
- Verification requires Ruff, mypy, and pytest to pass.

## File Map

```text
app/
  main.py                    FastAPI factory, middleware, exception handlers
  core/
    config.py                typed environment settings
    database.py              async engine/session dependency and base
    errors.py                application errors and HTTP serialization
    security.py              Argon2 and JWT primitives
  users/
    models.py                User and Role database types
    schemas.py               safe user response schemas
    repository.py            user persistence queries
  auth/
    schemas.py               registration, login, token payloads
    service.py               authentication use cases
    dependencies.py          current-user and admin dependencies
    router.py                /auth endpoints
  catalog/
    models.py                Category and Product tables
    schemas.py               catalog request/response schemas
    repository.py            catalog persistence and row locking
    service.py               catalog rules
    router.py                public/admin catalog endpoints
  cart/
    models.py                Cart and CartItem tables
    schemas.py               cart commands and projections
    repository.py            owned-cart persistence
    service.py               cart rules
    router.py                /cart endpoints
  orders/
    models.py                Order and OrderItem snapshots
    schemas.py               order projections
    repository.py            order persistence and owned reads
    service.py               atomic checkout
    router.py                /orders endpoints
  cli.py                     administrator creation/promotion command
alembic/                     migrations
tests/
  conftest.py                PostgreSQL transaction fixtures and API client
  unit/                      service-level tests
  integration/               database and concurrency tests
  api/                       end-to-end HTTP contract tests
```

---

### Task 1: Runnable Application Foundation

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/core/__init__.py`
- Create: `app/core/config.py`
- Create: `app/core/database.py`
- Create: `tests/conftest.py`
- Create: `tests/api/test_health.py`

**Interfaces:**
- Produces: `Settings`, `get_settings()`, `Base`, `async_session_factory`, `get_db()`, `create_app()`.
- Produces fixtures: `db_session`, `client`; `TEST_DATABASE_URL` must point to a disposable PostgreSQL database.

- [ ] **Step 1: Define dependencies and a failing health test**

```toml
# pyproject.toml
[project]
name = "ecommerce-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "alembic>=1.13,<2",
  "asyncpg>=0.29,<1",
  "email-validator>=2.2,<3",
  "fastapi>=0.115,<1",
  "pydantic-settings>=2.6,<3",
  "pyjwt>=2.9,<3",
  "pwdlib[argon2]>=0.2,<1",
  "sqlalchemy[asyncio]>=2.0.36,<3",
  "typer>=0.15,<1",
  "uvicorn[standard]>=0.32,<1",
]

[project.optional-dependencies]
dev = ["httpx>=0.28,<1", "mypy>=1.13,<2", "pytest>=8.3,<9", "pytest-asyncio>=0.24,<1", "pyyaml>=6,<7", "ruff>=0.8,<1"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
```

```python
# tests/api/test_health.py
from httpx import AsyncClient


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test and confirm the app fixture/import is missing**

Run: `pytest tests/api/test_health.py -v`

Expected: FAIL because `app.main.create_app` and the client fixture do not exist.

- [ ] **Step 3: Implement configuration, database lifecycle, app factory, and test fixtures**

```python
# app/core/config.py
from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://shop:shop@db:5432/shop"
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

```python
# app/core/database.py
from collections.abc import AsyncIterator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session
```

```python
# app/main.py
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Ecommerce API", version="0.1.0")

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

Implement `tests/conftest.py` with an async engine from `TEST_DATABASE_URL`, create/drop `Base.metadata` per test session, begin a transaction per test, override `get_db`, and expose `AsyncClient(transport=ASGITransport(app=create_app()))`. Fail immediately if `TEST_DATABASE_URL` is unset or does not contain a database name ending in `_test`.

- [ ] **Step 4: Verify the foundation**

Run: `JWT_SECRET=test TEST_DATABASE_URL=postgresql+asyncpg://shop:shop@localhost:5432/shop_test pytest tests/api/test_health.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example app tests
git commit -m "build: scaffold FastAPI application"
```

### Task 2: Unified Errors and Security Primitives

**Files:**
- Create: `app/core/errors.py`
- Create: `app/core/security.py`
- Modify: `app/main.py`
- Create: `tests/unit/core/test_security.py`
- Create: `tests/api/test_errors.py`

**Interfaces:**
- Produces: `AppError(code: str, message: str, status_code: int, details: dict[str, object])`.
- Produces: `hash_password(str) -> str`, `verify_password(str, str) -> bool`, `create_access_token(UUID, str) -> str`, `decode_access_token(str) -> TokenClaims`.

- [ ] **Step 1: Write failing password, token, and error-shape tests**

```python
def test_password_hash_is_verifiable() -> None:
    encoded = hash_password("long-enough-password")
    assert encoded != "long-enough-password"
    assert verify_password("long-enough-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_token_round_trip() -> None:
    user_id = uuid4()
    token = create_access_token(user_id, "customer")
    claims = decode_access_token(token)
    assert claims.sub == user_id
    assert claims.role == "customer"
```

Add an API-only test route that raises `AppError("sample_error", "Sample", 409, {"field": "email"})` and assert the exact nested JSON shape and status.

- [ ] **Step 2: Run tests and confirm missing symbols**

Run: `pytest tests/unit/core/test_security.py tests/api/test_errors.py -v`

Expected: FAIL on missing `app.core.security` and `app.core.errors`.

- [ ] **Step 3: Implement explicit error translation and security**

Use `pwdlib.PasswordHash.recommended()` for Argon2. Define a frozen `TokenClaims` dataclass with `sub: UUID`, `role: str`, `iat: datetime`, and `exp: datetime`. Decode with PyJWT while requiring `sub`, `role`, `iat`, and `exp`; convert all decode failures into `AppError("invalid_token", "Invalid or expired access token", 401)`.

Register handlers in `create_app()` for `AppError` and `RequestValidationError`. The latter must return status 422, code `validation_error`, and sanitized Pydantic error entries in `details["errors"]`.

- [ ] **Step 4: Run focused tests**

Run: `pytest tests/unit/core/test_security.py tests/api/test_errors.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/core app/main.py tests/unit/core tests/api/test_errors.py
git commit -m "feat: add security and API error contracts"
```

### Task 3: Users, Registration, Login, and Role Dependencies

**Files:**
- Create: `app/users/{__init__,models,schemas,repository}.py`
- Create: `app/auth/{__init__,schemas,service,dependencies,router}.py`
- Modify: `app/main.py`
- Create: `tests/api/test_auth.py`
- Create: `tests/unit/auth/test_service.py`

**Interfaces:**
- Produces: `Role(str, Enum)`, `User`, `UserRepository`.
- Produces: `AuthService.register(email, password) -> User`, `AuthService.authenticate(email, password) -> User`.
- Produces dependencies: `get_current_user(token, db) -> User`, `require_admin(user) -> User`.

- [ ] **Step 1: Write failing authentication contract tests**

```python
async def test_register_login_and_me(client: AsyncClient) -> None:
    registered = await client.post(
        "/api/v1/auth/register",
        json={"email": "Customer@Example.com", "password": "correct horse battery staple"},
    )
    assert registered.status_code == 201
    assert registered.json()["email"] == "customer@example.com"
    assert registered.json()["role"] == "customer"
    assert "password" not in registered.text

    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"email": "customer@example.com", "password": "correct horse battery staple"},
    )
    token = logged_in.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "customer@example.com"
```

Also assert duplicate email is 409 `email_conflict`, bad credentials are 401 `invalid_credentials`, registration ignores/rejects a supplied role, and an inactive user cannot authenticate.

- [ ] **Step 2: Run tests and confirm 404/missing models**

Run: `pytest tests/unit/auth/test_service.py tests/api/test_auth.py -v`

Expected: FAIL because auth routes and user persistence are absent.

- [ ] **Step 3: Implement users and authentication**

Define `User` with UUID primary key, case-insensitive unique normalized email, password hash, `Role`, `is_active`, and timestamps. `RegisterRequest` accepts only email/password with an 8-character minimum and forbids extra fields. `LoginRequest` accepts email/password. `TokenResponse` returns `access_token` and `token_type="bearer"`.

Normalize email with `email.strip().lower()`. Catch PostgreSQL uniqueness violations at the repository/service boundary and raise `email_conflict`. Login must use the same generic `invalid_credentials` response for missing users and bad passwords.

Mount the router at `/api/v1/auth`.

- [ ] **Step 4: Verify auth behavior**

Run: `pytest tests/unit/auth/test_service.py tests/api/test_auth.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/users app/auth app/main.py tests/unit/auth tests/api/test_auth.py
git commit -m "feat: add JWT authentication and roles"
```

### Task 4: Catalog Models, Public Queries, and Admin Mutations

**Files:**
- Create: `app/catalog/{__init__,models,schemas,repository,service,router}.py`
- Modify: `app/main.py`
- Create: `tests/unit/catalog/test_service.py`
- Create: `tests/api/test_catalog.py`

**Interfaces:**
- Produces: `Category`, `Product`.
- Produces: `CatalogService.create_category`, `update_category`, `delete_category`, `create_product`, `update_product`, `unpublish_product`.
- Produces: `CatalogRepository.lock_products(product_ids: list[UUID]) -> list[Product]` for checkout.

- [ ] **Step 1: Write failing public and admin catalog tests**

```python
async def test_public_sees_only_published_products(client, admin_headers) -> None:
    category = await client.post(
        "/api/v1/categories", headers=admin_headers, json={"name": "Phones", "slug": "phones"}
    )
    category_id = category.json()["id"]
    visible = await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "category_id": category_id,
            "name": "Phone",
            "slug": "phone",
            "description": "",
            "price": "499.90",
            "stock_quantity": 3,
            "is_published": True,
        },
    )
    await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "category_id": category_id,
            "name": "Draft",
            "slug": "draft",
            "description": "",
            "price": "10.00",
            "stock_quantity": 1,
            "is_published": False,
        },
    )
    response = await client.get("/api/v1/products")
    assert [item["id"] for item in response.json()["items"]] == [visible.json()["id"]]
```

Add tests for 403 customer writes, `limit/offset`, category filter, unique slug conflicts, nonnegative price/stock, missing products, soft delete, and 409 when deleting a nonempty category.

- [ ] **Step 2: Run tests and confirm catalog routes are absent**

Run: `pytest tests/unit/catalog/test_service.py tests/api/test_catalog.py -v`

Expected: FAIL with missing modules or 404 routes.

- [ ] **Step 3: Implement catalog boundaries**

Use `Numeric(12, 2)` and Pydantic `Decimal` constraints (`ge=0`, `decimal_places=2`). Validate slugs against `^[a-z0-9]+(?:-[a-z0-9]+)*$`. Public reads filter `is_published IS TRUE`. Admin delete for products updates `is_published`; category delete first checks for any products, including unpublished products.

Return lists as:

```json
{"items": [], "limit": 20, "offset": 0, "total": 0}
```

Order product results by `created_at DESC, id DESC`. Clamp neither parameter silently: reject `limit < 1`, `limit > 100`, and `offset < 0` with validation_error.

- [ ] **Step 4: Verify catalog behavior**

Run: `pytest tests/unit/catalog/test_service.py tests/api/test_catalog.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/catalog app/main.py tests/unit/catalog tests/api/test_catalog.py
git commit -m "feat: add public and admin catalog API"
```

### Task 5: Owned Cart

**Files:**
- Create: `app/cart/{__init__,models,schemas,repository,service,router}.py`
- Modify: `app/main.py`
- Create: `tests/unit/cart/test_service.py`
- Create: `tests/api/test_cart.py`

**Interfaces:**
- Produces: `Cart`, `CartItem`.
- Produces: `CartService.get(user_id)`, `add_item(user_id, product_id, quantity)`, `set_quantity(user_id, item_id, quantity)`, `remove_item(user_id, item_id)`.
- Produces: `CartRepository.get_or_create(user_id, *, for_update=False) -> Cart`.

- [ ] **Step 1: Write failing cart behavior and isolation tests**

```python
async def test_add_same_product_increments_quantity(
    client, customer_headers, published_product
) -> None:
    payload = {"product_id": str(published_product.id), "quantity": 1}
    assert (
        await client.post("/api/v1/cart/items", headers=customer_headers, json=payload)
    ).status_code == 201
    response = await client.post("/api/v1/cart/items", headers=customer_headers, json=payload)
    assert response.status_code == 200
    cart = (await client.get("/api/v1/cart", headers=customer_headers)).json()
    assert cart["items"][0]["quantity"] == 2
    assert cart["total"] == str(published_product.price * 2)
```

Add tests for empty auto-created cart, unpublished/missing product, quantity above stock, set quantity, delete, unknown or foreign item returning 404, and separate carts for separate users.

- [ ] **Step 2: Run tests and confirm missing cart implementation**

Run: `pytest tests/unit/cart/test_service.py tests/api/test_cart.py -v`

Expected: FAIL with missing modules or routes.

- [ ] **Step 3: Implement cart rules**

Create a unique constraint on `carts.user_id` and `(cart_id, product_id)`. `POST /cart/items` returns 201 for a new row and 200 when incrementing. Require positive quantity; reject requested aggregate quantity above stock with 409 `insufficient_stock`. Reject unpublished products as 404 `product_not_found`.

Serialize each item with product ID, name, unit price, quantity, and line total; serialize the cart total from current catalog prices. Repository queries must always constrain both item identity and the authenticated user's cart.

- [ ] **Step 4: Verify cart behavior**

Run: `pytest tests/unit/cart/test_service.py tests/api/test_cart.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/cart app/main.py tests/unit/cart tests/api/test_cart.py
git commit -m "feat: add customer cart API"
```

### Task 6: Atomic Checkout and Owned Order Reads

**Files:**
- Create: `app/orders/{__init__,models,schemas,repository,service,router}.py`
- Modify: `app/main.py`
- Create: `tests/unit/orders/test_service.py`
- Create: `tests/integration/test_checkout.py`
- Create: `tests/api/test_orders.py`

**Interfaces:**
- Produces: `OrderStatus.CREATED`, `Order`, `OrderItem`.
- Produces: `OrderService.checkout(user_id: UUID) -> Order`.
- Produces: `OrderRepository.list_owned(user_id, limit, offset)` and `get_owned(user_id, order_id)`.

- [ ] **Step 1: Write failing checkout and immutable-snapshot tests**

```python
async def test_checkout_creates_snapshot_decrements_stock_and_clears_cart(
    client, customer_headers, product_in_cart, db_session
) -> None:
    response = await client.post("/api/v1/orders/checkout", headers=customer_headers)
    assert response.status_code == 201
    order = response.json()
    assert order["status"] == "created"
    assert order["items"][0]["product_name"] == product_in_cart.name
    assert order["items"][0]["unit_price"] == str(product_in_cart.price)
    assert order["total"] == order["items"][0]["line_total"]
    assert (await client.get("/api/v1/cart", headers=customer_headers)).json()["items"] == []
    await db_session.refresh(product_in_cart)
    assert product_in_cart.stock_quantity == 0
```

Add tests for empty cart (400 `empty_cart`), unpublished product (409 `product_unavailable`), insufficient stock (409), rollback preserving cart and stock, order ownership, order list pagination, and changing a product after checkout without changing the snapshot.

- [ ] **Step 2: Run focused tests and confirm missing order implementation**

Run: `pytest tests/unit/orders/test_service.py tests/integration/test_checkout.py tests/api/test_orders.py -v`

Expected: FAIL with missing modules or routes.

- [ ] **Step 3: Implement the transaction**

Within the request's `AsyncSession`, have `checkout`:

```python
async with session.begin_nested():
    cart = await cart_repository.get_or_create(user_id, for_update=True)
    items = await cart_repository.list_items(cart.id)
    if not items:
        raise AppError("empty_cart", "Cart is empty", 400)
    products = await catalog_repository.lock_products(sorted(item.product_id for item in items))
    # Map products, validate every item, calculate Decimal line totals,
    # create Order/OrderItem snapshots, decrement stock, delete cart items.
await session.commit()
```

Implement the validation/calculation block explicitly: ensure every cart item maps to a published product, ensure `stock_quantity >= quantity`, quantize each multiplication to `Decimal("0.01")`, and sum line totals into `orders.total`. Store `product_id`, `product_name`, `unit_price`, `quantity`, and `line_total` on every order item.

Read queries constrain `Order.user_id == current_user.id`; an absent or foreign order produces the same 404 `order_not_found`.

- [ ] **Step 4: Add and run a real concurrency test**

Open two independent async sessions, place the final unit of one product into two users' carts, synchronize two checkout coroutines with an `asyncio.Event`, and run `asyncio.gather`. Assert exactly one succeeds, one raises `insufficient_stock`, the final stock is zero, and only one order exists.

Run: `pytest tests/integration/test_checkout.py -v`

Expected: PASS against PostgreSQL (do not substitute SQLite).

- [ ] **Step 5: Run all order tests**

Run: `pytest tests/unit/orders/test_service.py tests/integration/test_checkout.py tests/api/test_orders.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/orders app/main.py tests/unit/orders tests/integration/test_checkout.py tests/api/test_orders.py
git commit -m "feat: add atomic order checkout"
```

### Task 7: Alembic Schema and Administrator CLI

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/versions/20260727_0001_initial_schema.py`
- Create: `app/cli.py`
- Modify: `pyproject.toml`
- Create: `tests/integration/test_migrations.py`
- Create: `tests/integration/test_admin_cli.py`

**Interfaces:**
- Produces console command: `shop-admin create-or-promote --email EMAIL --password PASSWORD`.
- Produces a reversible initial Alembic migration for every table, enum, constraint, index, and foreign key.

- [ ] **Step 1: Write failing migration and CLI tests**

Migration test: run `alembic upgrade head`, inspect PostgreSQL, and assert the tables `users`, `categories`, `products`, `carts`, `cart_items`, `orders`, `order_items`, and `alembic_version`; then run downgrade to base and assert application tables are gone.

CLI test: invoke the Typer runner twice with the same email—first creates an admin, second promotes/updates idempotently—and assert exactly one normalized user with role `admin`.

- [ ] **Step 2: Run tests and confirm Alembic/CLI files are missing**

Run: `pytest tests/integration/test_migrations.py tests/integration/test_admin_cli.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement migration and CLI**

Import every model in `alembic/env.py`, set `target_metadata = Base.metadata`, and use an async migration connection. Hand-author the initial migration so upgrade order follows foreign keys and downgrade is exactly reversed. Include unique constraints, check constraints for nonnegative price/stock and positive quantities, and indexes used by product and order listing.

Add:

```toml
[project.scripts]
shop-admin = "app.cli:app"
```

The CLI accepts `--password` as a hidden Typer option with `prompt=True`, so omitting it triggers an interactive hidden prompt. It normalizes email, hashes the password, creates or promotes the user, sets `is_active=True`, commits, and prints only the email and outcome—never the password or hash.

- [ ] **Step 4: Verify migrations and CLI**

Run: `pytest tests/integration/test_migrations.py tests/integration/test_admin_cli.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alembic.ini alembic app/cli.py pyproject.toml tests/integration
git commit -m "feat: add database migration and admin CLI"
```

### Task 8: Containerized Runtime and Operator Documentation

**Files:**
- Create: `Dockerfile`
- Create: `compose.yaml`
- Create: `.dockerignore`
- Create: `README.md`
- Modify: `.env.example`
- Create: `tests/smoke/test_compose_config.py`

**Interfaces:**
- Produces services: `api` on port 8000 and `db` on PostgreSQL 16.
- Documents setup, migration, admin creation, testing, and representative curl requests.

- [ ] **Step 1: Write a failing Compose configuration test**

```python
def test_compose_has_healthchecks_and_no_embedded_secret() -> None:
    result = subprocess.run(
        ["docker", "compose", "config"], check=True, capture_output=True, text=True
    )
    config = yaml.safe_load(result.stdout)
    assert set(config["services"]) == {"api", "db"}
    assert "healthcheck" in config["services"]["db"]
    assert "JWT_SECRET" in config["services"]["api"]["environment"]
    assert config["services"]["api"]["depends_on"]["db"]["condition"] == "service_healthy"
```

- [ ] **Step 2: Run the smoke test and confirm Compose is absent**

Run: `pytest tests/smoke/test_compose_config.py -v`

Expected: FAIL because `compose.yaml` does not exist.

- [ ] **Step 3: Implement runtime packaging**

Use `python:3.12-slim`, install the project in a virtual environment, run as a non-root user, expose 8000, and start `uvicorn app.main:app --host 0.0.0.0 --port 8000`. Compose uses `postgres:16`, a named volume, a `pg_isready` health check, environment interpolation, and no literal production secret. The API waits for healthy PostgreSQL and runs `alembic upgrade head` before Uvicorn.

Populate `.env.example` with safe local placeholders for `DATABASE_URL`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `JWT_SECRET`, and `ACCESS_TOKEN_MINUTES`.

- [ ] **Step 4: Document exact operator and API workflows**

README must include:

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec api alembic upgrade head
docker compose exec api shop-admin create-or-promote --email admin@example.com
pytest
ruff check .
mypy app
```

Also document `/docs`, registration/login, bearer authentication, category/product creation, cart addition, checkout, error JSON, and the requirement for a disposable `*_test` PostgreSQL database.

- [ ] **Step 5: Verify Compose rendering**

Run: `pytest tests/smoke/test_compose_config.py -v && docker compose config --quiet`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add Dockerfile compose.yaml .dockerignore .env.example README.md tests/smoke
git commit -m "docs: add containerized local operations"
```

### Task 9: CI and Full Acceptance Verification

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: tests only if acceptance verification exposes a test defect; production fixes require returning to the responsible task's RED/GREEN cycle.

**Interfaces:**
- Produces CI checks for Ruff, mypy, migrations, and all tests using PostgreSQL 16.

- [ ] **Step 1: Add a CI workflow with a PostgreSQL service**

Configure pull request and push triggers, Python 3.12, dependency caching, PostgreSQL 16 with health checks, and environment values for `DATABASE_URL`, `TEST_DATABASE_URL`, and `JWT_SECRET`.

Run these exact jobs/steps:

```bash
ruff check .
ruff format --check .
mypy app
alembic upgrade head
pytest -v
```

- [ ] **Step 2: Run static checks locally**

Run: `ruff check . && ruff format --check . && mypy app`

Expected: all commands exit 0.

- [ ] **Step 3: Prove migrations from an empty database**

Run against a newly created disposable database:

```bash
alembic upgrade head
alembic downgrade base
alembic upgrade head
```

Expected: all commands exit 0 and the final schema is at head.

- [ ] **Step 4: Run the complete test suite**

Run: `pytest -v`

Expected: PASS with unit, API, integration, migration, concurrency, CLI, and smoke tests all collected.

- [ ] **Step 5: Perform a container smoke test**

Run:

```bash
docker compose up --build -d
docker compose exec api alembic current
curl --fail http://localhost:8000/health
docker compose down
```

Expected: Alembic reports head and health returns `{"status":"ok"}`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: verify ecommerce API"
```

- [ ] **Step 7: Record final evidence**

Run: `git status --short && git log --oneline --decorate -10`

Expected: clean worktree and one focused commit for each completed task.
