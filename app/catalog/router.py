from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.catalog.models import Category, Product
from app.catalog.repository import CatalogRepository
from app.catalog.schemas import (
    CategoryCreate,
    CategoryListResponse,
    CategoryResponse,
    CategoryUpdate,
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.catalog.service import CatalogService
from app.core.database import get_db
from app.core.errors import AppError
from app.users.models import User

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _catalog_service(db: AsyncSession) -> CatalogService:
    return CatalogService(CatalogRepository(db))


@router.get("/categories", response_model=CategoryListResponse)
async def list_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CategoryListResponse:
    items, total = await CatalogRepository(db).list_categories(limit, offset)
    return CategoryListResponse(items=list(items), limit=limit, offset=offset, total=total)


@router.post("/categories", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    request: CategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> Category:
    return await _catalog_service(db).create_category(request.name, request.slug)


@router.patch("/categories/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: UUID,
    request: CategoryUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> Category:
    return await _catalog_service(db).update_category(
        category_id, **request.model_dump(exclude_unset=True)
    )


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> Response:
    await _catalog_service(db).delete_category(category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductListResponse:
    items, total = await CatalogRepository(db).list_published_products(category_id, limit, offset)
    return ProductListResponse(items=list(items), limit=limit, offset=offset, total=total)


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(product_id: UUID, db: Annotated[AsyncSession, Depends(get_db)]) -> Product:
    product = await CatalogRepository(db).get_published_product(product_id)
    if product is None:
        raise AppError("product_not_found", "Product not found", 404)
    return product


@router.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> Product:
    return await _catalog_service(db).create_product(**request.model_dump())


@router.patch("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    request: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> Product:
    return await _catalog_service(db).update_product(
        product_id, **request.model_dump(exclude_unset=True)
    )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_admin)],
) -> Response:
    await _catalog_service(db).unpublish_product(product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
