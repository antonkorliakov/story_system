from typing import cast
from uuid import uuid4

import pytest
from httpx import AsyncClient, Response


async def _create_category(client: AsyncClient, admin_headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/categories", headers=admin_headers, json={"name": "Phones", "slug": "phones"}
    )
    assert response.status_code == 201
    return cast(str, response.json()["id"])


async def _create_product(
    client: AsyncClient,
    admin_headers: dict[str, str],
    category_id: str,
    *,
    name: str = "Phone",
    slug: str = "phone",
    is_published: bool = True,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "category_id": category_id,
            "name": name,
            "slug": slug,
            "description": "",
            "price": "499.90",
            "stock_quantity": 3,
            "is_published": is_published,
        },
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.json())


async def test_public_sees_only_published_products(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    category_id = await _create_category(client, admin_headers)
    visible = await _create_product(client, admin_headers, category_id)
    await _create_product(
        client, admin_headers, category_id, name="Draft", slug="draft", is_published=False
    )

    response = await client.get("/api/v1/products")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [visible["id"]]
    assert response.json()["limit"] == 20
    assert response.json()["offset"] == 0
    assert response.json()["total"] == 1


async def test_customer_cannot_write_catalog(
    client: AsyncClient, customer_headers: dict[str, str]
) -> None:
    response = await client.post(
        "/api/v1/categories", headers=customer_headers, json={"name": "Phones", "slug": "phones"}
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_public_products_honor_category_filter_and_pagination(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    phones = await _create_category(client, admin_headers)
    laptops_response = await client.post(
        "/api/v1/categories", headers=admin_headers, json={"name": "Laptops", "slug": "laptops"}
    )
    laptops = laptops_response.json()["id"]
    first = await _create_product(client, admin_headers, phones, name="Phone 1", slug="phone-1")
    await _create_product(client, admin_headers, phones, name="Phone 2", slug="phone-2")
    await _create_product(client, admin_headers, laptops, name="Laptop", slug="laptop")

    filtered = await client.get(f"/api/v1/products?category_id={phones}&limit=1&offset=1")

    assert filtered.status_code == 200
    assert filtered.json()["limit"] == 1
    assert filtered.json()["offset"] == 1
    assert filtered.json()["total"] == 2
    assert [item["category_id"] for item in filtered.json()["items"]] == [phones]
    assert filtered.json()["items"][0]["id"] == first["id"]


@pytest.mark.parametrize("params", ["limit=0", "limit=101", "offset=-1"])
async def test_invalid_product_pagination_returns_validation_error(
    client: AsyncClient, params: str
) -> None:
    response = await client.get(f"/api/v1/products?{params}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_duplicate_product_slug_returns_conflict(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    category_id = await _create_category(client, admin_headers)
    await _create_product(client, admin_headers, category_id)

    duplicate = await _create_product_request(client, admin_headers, category_id, slug="phone")

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "product_slug_conflict"


async def test_product_creation_rejects_negative_price_and_stock(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    category_id = await _create_category(client, admin_headers)
    response = await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "category_id": category_id,
            "name": "Phone",
            "slug": "phone",
            "description": "",
            "price": "-0.01",
            "stock_quantity": -1,
            "is_published": True,
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_missing_and_unpublished_products_are_not_public(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    missing = await client.get(f"/api/v1/products/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "product_not_found"

    category_id = await _create_category(client, admin_headers)
    product = await _create_product(client, admin_headers, category_id)
    removed = await client.delete(f"/api/v1/products/{product['id']}", headers=admin_headers)
    hidden = await client.get(f"/api/v1/products/{product['id']}")

    assert removed.status_code == 204
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "product_not_found"


async def test_cannot_delete_nonempty_category(
    client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    category_id = await _create_category(client, admin_headers)
    await _create_product(client, admin_headers, category_id, is_published=False)

    response = await client.delete(f"/api/v1/categories/{category_id}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "category_not_empty"


async def _create_product_request(
    client: AsyncClient, admin_headers: dict[str, str], category_id: str, slug: str
) -> Response:
    return await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "category_id": category_id,
            "name": "Phone duplicate",
            "slug": slug,
            "description": "",
            "price": "499.90",
            "stock_quantity": 3,
            "is_published": True,
        },
    )
