from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.users.models import Role, User


async def _product(
    client: AsyncClient,
    admin_headers: dict[str, str],
    *,
    slug: str = "order-phone",
    stock_quantity: int = 2,
    is_published: bool = True,
) -> dict[str, object]:
    category = await client.post(
        "/api/v1/categories",
        headers=admin_headers,
        json={"name": f"Category {slug}", "slug": f"category-{slug}"},
    )
    assert category.status_code == 201
    response = await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "category_id": category.json()["id"],
            "name": "Phone",
            "slug": slug,
            "description": "",
            "price": "499.90",
            "stock_quantity": stock_quantity,
            "is_published": is_published,
        },
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def _add(
    client: AsyncClient,
    headers: dict[str, str],
    product_id: object,
    quantity: int = 1,
) -> None:
    response = await client.post(
        "/api/v1/cart/items",
        headers=headers,
        json={"product_id": product_id, "quantity": quantity},
    )
    assert response.status_code == 201


async def test_checkout_endpoint_creates_order_and_snapshot(
    client: AsyncClient, admin_headers: dict[str, str], customer_headers: dict[str, str]
) -> None:
    product = await _product(client, admin_headers)
    await _add(client, customer_headers, product["id"], 2)

    response = await client.post("/api/v1/orders/checkout", headers=customer_headers)

    assert response.status_code == 201
    assert response.json()["status"] == "created"
    assert response.json()["total"] == "999.80"
    assert response.json()["items"][0]["product_name"] == "Phone"
    assert response.json()["items"][0]["unit_price"] == "499.90"
    assert response.json()["items"][0]["line_total"] == "999.80"
    assert (await client.get("/api/v1/cart", headers=customer_headers)).json()["items"] == []


@pytest.mark.parametrize(
    ("prepare", "expected_status", "expected_code"),
    [
        ("empty", 400, "empty_cart"),
        ("unpublished", 409, "product_unavailable"),
        ("insufficient", 409, "insufficient_stock"),
    ],
)
async def test_checkout_validation_errors(
    client: AsyncClient,
    admin_headers: dict[str, str],
    customer_headers: dict[str, str],
    prepare: str,
    expected_status: int,
    expected_code: str,
) -> None:
    if prepare != "empty":
        product = await _product(client, admin_headers, slug=f"validation-{prepare}")
        await _add(client, customer_headers, product["id"])
        if prepare == "unpublished":
            assert (
                await client.delete(f"/api/v1/products/{product['id']}", headers=admin_headers)
            ).status_code == 204
        else:
            assert (
                await client.patch(
                    f"/api/v1/products/{product['id']}",
                    headers=admin_headers,
                    json={"stock_quantity": 0},
                )
            ).status_code == 200

    response = await client.post("/api/v1/orders/checkout", headers=customer_headers)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


async def test_order_reads_enforce_ownership_and_paginate(
    client: AsyncClient,
    admin_headers: dict[str, str],
    customer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    second = User(
        email=f"order-reader-{uuid4()}@example.com",
        password_hash=hash_password("correct horse battery staple"),
        role=Role.CUSTOMER,
    )
    db_session.add(second)
    await db_session.flush()
    second_headers = {
        "Authorization": f"Bearer {create_access_token(second.id, second.role.value)}"
    }
    first_product = await _product(client, admin_headers, slug="pagination-first")
    second_product = await _product(client, admin_headers, slug="pagination-second")
    await _add(client, customer_headers, first_product["id"])
    first_order = await client.post("/api/v1/orders/checkout", headers=customer_headers)
    await _add(client, customer_headers, second_product["id"])
    second_order = await client.post("/api/v1/orders/checkout", headers=customer_headers)

    page = await client.get("/api/v1/orders?limit=1&offset=1", headers=customer_headers)
    foreign = await client.get(f"/api/v1/orders/{first_order.json()['id']}", headers=second_headers)
    missing = await client.get(f"/api/v1/orders/{uuid4()}", headers=customer_headers)

    assert first_order.status_code == second_order.status_code == 201
    assert page.status_code == 200
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert page.json()["total"] == 2
    assert page.json()["items"][0]["id"] == first_order.json()["id"]
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["error"]["code"] == "order_not_found"
    assert missing.json()["error"]["code"] == "order_not_found"


async def test_product_changes_do_not_change_an_order_snapshot(
    client: AsyncClient, admin_headers: dict[str, str], customer_headers: dict[str, str]
) -> None:
    product = await _product(client, admin_headers, slug="snapshot-product")
    await _add(client, customer_headers, product["id"])
    checkout = await client.post("/api/v1/orders/checkout", headers=customer_headers)

    changed = await client.patch(
        f"/api/v1/products/{product['id']}",
        headers=admin_headers,
        json={"name": "New name", "price": "1.00"},
    )
    loaded = await client.get(f"/api/v1/orders/{checkout.json()['id']}", headers=customer_headers)

    assert changed.status_code == 200
    assert loaded.status_code == 200
    assert loaded.json()["items"][0]["product_name"] == "Phone"
    assert loaded.json()["items"][0]["unit_price"] == "499.90"
