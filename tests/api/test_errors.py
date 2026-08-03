from typing import Annotated

from fastapi import Body
from httpx import ASGITransport, AsyncClient

from app.core.errors import AppError
from app.main import create_app


async def test_app_error_has_the_documented_nested_json_shape() -> None:
    app = create_app()

    @app.get("/test/error")
    async def error_route() -> None:
        raise AppError("sample_error", "Sample", 409, {"field": "email"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/test/error")

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "sample_error",
            "message": "Sample",
            "details": {"field": "email"},
        }
    }


async def test_request_validation_errors_are_sanitized() -> None:
    app = create_app()

    @app.post("/test/validation")
    async def validation_route(value: Annotated[int, Body()]) -> dict[str, int]:
        return {"value": value}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/test/validation", json="not-an-integer")

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    validation_error = body["error"]["details"]["errors"][0]
    assert validation_error["type"] == "int_parsing"
    assert validation_error["loc"] == ["body"]
    assert isinstance(validation_error["msg"], str)
    assert set(validation_error) == {"type", "loc", "msg"}
