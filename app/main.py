from collections.abc import Sequence

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.cart.router import router as cart_router
from app.catalog.router import router as catalog_router
from app.core.errors import AppError
from app.orders.router import router as orders_router


def create_app() -> FastAPI:
    app = FastAPI(title="Ecommerce API", version="0.1.0")

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, error: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Request validation failed",
                    "details": {"errors": _sanitize_validation_errors(error.errors())},
                }
            },
        )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(catalog_router)
    app.include_router(cart_router)
    app.include_router(orders_router)

    return app


def _sanitize_validation_errors(errors: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "type": error["type"],
            "loc": list(error["loc"]) if isinstance(error["loc"], tuple) else error["loc"],
            "msg": error["msg"],
        }
        for error in errors
    ]


app = create_app()
