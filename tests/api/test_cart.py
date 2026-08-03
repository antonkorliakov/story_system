from typing import cast
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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
    slug: str = "phone",
    is_published: bool = True,
    stock_quantity: int = 3,
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/products",
        headers=admin_headers,
        json={
            "category_id": category_id,
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


async def _published_product(
    client: AsyncClient, admin_headers: dict[str, str]
) -> dict[str, object]:
    return await _create_product(
        client, admin_headers, await _create_category(client, admin_headers)
    )


async def test_get_cart_auto_creates_an_empty_cart(
    client: AsyncClient, customer_headers: dict[str, str]
) -> None:
    response = await client.get("/api/v1/cart", headers=customer_headers)

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["total"] == "0.00"


async def test_add_same_product_increments_quantity(
    client: AsyncClient, admin_headers: dict[str, str], customer_headers: dict[str, str]
) -> None:
    product = await _published_product(client, admin_headers)
    payload = {"product_id": product["id"], "quantity": 1}

    assert (
        await client.post("/api/v1/cart/items", headers=customer_headers, json=payload)
    ).status_code == 201
    response = await client.post("/api/v1/cart/items", headers=customer_headers, json=payload)
    cart = await client.get("/api/v1/cart", headers=customer_headers)

    assert response.status_code == 200
    assert cart.status_code == 200
    assert cart.json()["items"] == [
        {
            "id": response.json()["id"],
            "product_id": product["id"],
            "name": "Phone",
            "unit_price": "499.90",
            "quantity": 2,
            "line_total": "999.80",
        }
    ]
    assert cart.json()["total"] == "999.80"


async def test_add_item_rejects_missing_unpublished_and_overstock_products(
    client: AsyncClient, admin_headers: dict[str, str], customer_headers: dict[str, str]
) -> None:
    category_id = await _create_category(client, admin_headers)
    unpublished = await _create_product(
        client, admin_headers, category_id, slug="draft", is_published=False
    )
    limited = await _create_product(
        client, admin_headers, category_id, slug="limited", stock_quantity=1
    )

    missing = await client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": str(uuid4()), "quantity": 1},
    )
    draft = await client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": unpublished["id"], "quantity": 1},
    )
    overstock = await client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": limited["id"], "quantity": 2},
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "product_not_found"
    assert draft.status_code == 404
    assert draft.json()["error"]["code"] == "product_not_found"
    assert overstock.status_code == 409
    assert overstock.json()["error"]["code"] == "insufficient_stock"


async def test_get_cart_rejects_items_when_an_admin_unpublishes_the_product(
    client: AsyncClient, admin_headers: dict[str, str], customer_headers: dict[str, str]
) -> None:
    product = await _published_product(client, admin_headers)
    product_id = product["id"]
    added = await client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": product_id, "quantity": 1},
    )
    unpublished = await client.delete(f"/api/v1/products/{product_id}", headers=admin_headers)
    cart = await client.get("/api/v1/cart", headers=customer_headers)

    assert added.status_code == 201
    assert unpublished.status_code == 204
    assert cart.status_code == 404
    assert cart.json()["error"]["code"] == "product_not_found"


async def test_set_and_delete_cart_item_enforce_ownership(
    client: AsyncClient,
    admin_headers: dict[str, str],
    customer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    product = await _published_product(client, admin_headers)
    added = await client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": product["id"], "quantity": 1},
    )
    item_id = added.json()["id"]

    changed = await client.patch(
        f"/api/v1/cart/items/{item_id}", headers=customer_headers, json={"quantity": 3}
    )
    deleted = await client.delete(f"/api/v1/cart/items/{item_id}", headers=customer_headers)
    unknown = await client.delete(f"/api/v1/cart/items/{uuid4()}", headers=customer_headers)

    assert changed.status_code == 200
    assert changed.json()["quantity"] == 3
    assert deleted.status_code == 204
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "cart_item_not_found"


async def test_separate_users_have_separate_carts(
    client: AsyncClient,
    admin_headers: dict[str, str],
    customer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    product = await _published_product(client, admin_headers)
    added = await client.post(
        "/api/v1/cart/items",
        headers=customer_headers,
        json={"product_id": product["id"], "quantity": 1},
    )
    from app.core.security import create_access_token, hash_password
    from app.users.models import Role, User

    second = User(
        email="second@example.com",
        password_hash=hash_password("correct horse battery staple"),
        role=Role.CUSTOMER,
    )
    db_session.add(second)
    await db_session.flush()
    second_headers = {
        "Authorization": f"Bearer {create_access_token(second.id, second.role.value)}"
    }
    item_id = added.json()["id"]

    foreign = await client.patch(
        f"/api/v1/cart/items/{item_id}", headers=second_headers, json={"quantity": 2}
    )
    second_cart = await client.get("/api/v1/cart", headers=second_headers)

    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "cart_item_not_found"
    assert second_cart.status_code == 200
    assert second_cart.json()["items"] == []
