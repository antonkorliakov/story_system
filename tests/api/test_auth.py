from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import create_app
from app.users.models import User


async def test_missing_token_uses_the_unified_invalid_token_envelope() -> None:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_token",
            "message": "Invalid or expired access token",
            "details": {},
        }
    }


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

    assert logged_in.status_code == 200
    token = logged_in.json()["access_token"]
    assert logged_in.json()["token_type"] == "bearer"
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert me.status_code == 200
    assert me.json()["email"] == "customer@example.com"
    assert "password" not in me.text


async def test_register_rejects_duplicate_normalized_email(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "customer@example.com", "password": "correct horse battery staple"},
    )

    duplicate = await client.post(
        "/api/v1/auth/register",
        json={"email": "Customer@Example.com", "password": "another correct password"},
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_conflict"


async def test_login_rejects_bad_credentials(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "not-the-password"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_register_rejects_a_client_supplied_role(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "admin@example.com",
            "password": "correct horse battery staple",
            "role": "admin",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_inactive_user_cannot_log_in(client: AsyncClient, db_session: AsyncSession) -> None:
    from app.core.security import hash_password
    from app.users.models import Role, User

    db_session.add(
        User(
            email="inactive@example.com",
            password_hash=hash_password("correct horse battery staple"),
            role=Role.CUSTOMER,
            is_active=False,
        )
    )
    await db_session.flush()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "correct horse battery staple"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


async def test_valid_token_is_rejected_after_the_user_is_deactivated(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "deactivated@example.com", "password": "correct horse battery staple"},
    )
    logged_in = await client.post(
        "/api/v1/auth/login",
        json={"email": "deactivated@example.com", "password": "correct horse battery staple"},
    )
    token = logged_in.json()["access_token"]
    user = (
        await db_session.execute(select(User).where(User.email == "deactivated@example.com"))
    ).scalar_one()
    user.is_active = False
    await db_session.flush()

    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_token",
            "message": "Invalid or expired access token",
            "details": {},
        }
    }
