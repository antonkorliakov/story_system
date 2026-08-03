# Final Branch Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the final migration-safety, fixture-discovery, authentication-envelope, test-isolation, and ORM/migration-parity findings without adding features.

**Architecture:** Preserve explicitly programmatic Alembic URLs while allowing the checked-in ini placeholder to be replaced by the runtime environment. Centralize API identity fixtures at the API conftest boundary, make every destructive migration test restore head in `finally`, normalize missing bearer credentials in the authentication dependency, and declare migration check constraints in ORM metadata.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy asyncio, Alembic, PostgreSQL 16, pytest, Ruff, mypy.

## Global Constraints

- Never connect to or drop a non-test database from destructive tests.
- Do not substitute SQLite for PostgreSQL integration coverage.
- Use exact unified errors: `{"error":{"code","message","details"}}`.
- Finish with non-database tests, full collection, Ruff format/check, and strict mypy.

---

### Task 1: Preserve Explicit Alembic URLs

**Files:**
- Modify: `tests/unit/test_migration_config.py`
- Modify: `app/core/migrations.py`

**Interfaces:**
- Consumes: `configure_database_url(Config) -> str`
- Produces: explicit `Config.set_main_option("sqlalchemy.url", ...)` precedence over ambient `DATABASE_URL`

- [ ] Add a test with ambient non-test `DATABASE_URL` and explicit `*_test` Config URL; assert the test URL remains configured.
- [ ] Run the focused test and confirm it fails by selecting the ambient URL.
- [ ] Compare the current Config URL with the checked-in ini URL; only the ini default may be replaced from the environment.
- [ ] Re-run all migration-config unit tests.

### Task 2: Centralize API Authentication Fixtures

**Files:**
- Modify: `tests/conftest.py`
- Modify: `tests/api/test_catalog.py`

**Interfaces:**
- Produces: `admin_headers` and `customer_headers` fixtures visible to every API test module

- [ ] Demonstrate cart/order fixture lookup failure with pytest setup planning.
- [ ] Move the two fixtures unchanged into root `tests/conftest.py` and remove duplicates/imports.
- [ ] Re-run setup planning and full collection to verify provider resolution.

### Task 3: Restore Shared Schema After Destructive Tests

**Files:**
- Modify: `tests/integration/test_admin_cli.py`
- Modify: `tests/integration/test_migrations.py`

**Interfaces:**
- Produces: destructive tests that always leave the configured test database at Alembic head

- [ ] Move destructive setup inside `try`.
- [ ] Keep downgrade assertions in the migration test, then call `command.upgrade(config, "head")` from `finally`.
- [ ] Make the admin CLI test restore head from `finally`, including assertion failures.
- [ ] Collect both PostgreSQL tests; execute only when PostgreSQL is available.

### Task 4: Normalize Missing and Deactivated Token Errors

**Files:**
- Modify: `tests/api/test_auth.py`
- Modify: `app/auth/dependencies.py`

**Interfaces:**
- Produces: missing bearer token and deactivated-user token responses as `invalid_token` 401 envelopes

- [ ] Add API tests for a missing token exact envelope and a valid token whose user is later deactivated.
- [ ] Confirm the missing-token test currently returns FastAPI's `{"detail":"Not authenticated"}` response.
- [ ] Set `OAuth2PasswordBearer(auto_error=False)`, accept `str | None`, and raise `AppError` when absent.
- [ ] Re-run non-database dependency/unit coverage and collect the API tests.

### Task 5: Align ORM Check Constraints with Migration Metadata

**Files:**
- Create: `tests/unit/test_model_constraints.py`
- Modify: `app/catalog/models.py`
- Modify: `app/cart/models.py`
- Modify: `app/orders/models.py`

**Interfaces:**
- Produces ORM constraints named `ck_products_price_nonnegative`, `ck_products_stock_quantity_nonnegative`, `ck_cart_items_quantity_positive`, and `ck_order_items_quantity_positive`

- [ ] Add a metadata-level test asserting the four constraint names.
- [ ] Run it and confirm the ORM metadata is missing those names.
- [ ] Add matching SQLAlchemy `CheckConstraint` declarations.
- [ ] Re-run the focused parity test.

### Task 6: Verification, Report, and Commit

**Files:**
- Create: `.superpowers/sdd/2026-07-27-ecommerce-rest-api/final-fix-report.md`

- [ ] Run all non-database tests and `pytest --collect-only`.
- [ ] Run `ruff format --check .`, `ruff check .`, and `mypy app`.
- [ ] Attempt PostgreSQL tests only against the required asyncpg `*_test` URL; document the exact blocker if unavailable.
- [ ] Review `git diff --check` and the complete scoped diff.
- [ ] Commit all final fixes and record the commit plus evidence in the report.
