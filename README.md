# Ecommerce API

FastAPI and PostgreSQL API for product catalogues, customer carts, and atomic checkout.

## Run locally with Docker Compose

Docker Engine with the Compose plugin is required. The database is PostgreSQL 16 and is stored in the named `postgres_data` volume. The API starts only after PostgreSQL is healthy, applies `alembic upgrade head`, then serves HTTP on port 8000.

```bash
cp .env.example .env
docker compose up --build -d
```

Open <http://localhost:8000/docs> for the interactive OpenAPI documentation, or verify the service:

```bash
curl http://localhost:8000/health
```

The Compose startup command already applies migrations. These explicit commands are useful for an operator check or a manual re-run:

```bash
docker compose exec api alembic upgrade head
docker compose exec api shop-admin create-or-promote --email admin@example.com
```

The administrator command prompts for a password. Stop the stack with `docker compose down`; add `--volumes` only when intentionally deleting local database data.

## API workflow

All API routes are under `/api/v1`. Register a customer and save the returned access token:

```bash
curl -sS -X POST http://localhost:8000/api/v1/auth/register \
  -H 'content-type: application/json' \
  -d '{"email":"customer@example.com","password":"correct-horse-battery-staple"}'

TOKEN=$(curl -sS -X POST http://localhost:8000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"customer@example.com","password":"correct-horse-battery-staple"}' \
  | python -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
```

Use a bearer token on protected routes:

```bash
curl -sS http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

Create an administrator by using the CLI command above (it creates or promotes the account), then log in as that account and set `ADMIN_TOKEN` from its login response. Create a category and a published product:

```bash
CATEGORY=$(curl -sS -X POST http://localhost:8000/api/v1/categories \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'content-type: application/json' \
  -d '{"name":"Books","slug":"books"}')

CATEGORY_ID=$(printf '%s' "$CATEGORY" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
PRODUCT=$(curl -sS -X POST http://localhost:8000/api/v1/products \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H 'content-type: application/json' \
  -d "{\"category_id\":\"$CATEGORY_ID\",\"name\":\"Example Book\",\"slug\":\"example-book\",\"description\":\"A book\",\"price\":19.99,\"stock_quantity\":10,\"is_published\":true}")

PRODUCT_ID=$(printf '%s' "$PRODUCT" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
```

Add the product to the customer cart and check out:

```bash
curl -sS -X POST http://localhost:8000/api/v1/cart/items \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d "{\"product_id\":\"$PRODUCT_ID\",\"quantity\":1}"

curl -sS -X POST http://localhost:8000/api/v1/orders/checkout \
  -H "Authorization: Bearer $TOKEN"
```

Application errors use this shape (validation errors use `validation_error` and include field errors in `details.errors`):

```json
{
  "error": {
    "code": "product_not_found",
    "message": "Product not found",
    "details": {}
  }
}
```

## Development and tests

Install the project with its development extras in a Python 3.12 environment, then use a disposable PostgreSQL database whose name ends in `_test`. Set `TEST_DATABASE_URL` to its asyncpg URL; tests refuse any database without that suffix.

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://shop:shop@localhost:5432/shop_test
export JWT_SECRET=test-only-secret
pytest
ruff check .
mypy app
```

Do not point `TEST_DATABASE_URL` at a shared or production database: the suite creates and drops its schema.
