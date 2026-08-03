from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.catalog.models import Category, Product
from app.catalog.repository import CatalogRepository
from app.core.errors import AppError


class CatalogService:
    def __init__(self, catalog: CatalogRepository) -> None:
        self._catalog = catalog

    async def create_category(self, name: str, slug: str) -> Category:
        if await self._catalog.get_category_by_slug(slug) is not None:
            raise _category_slug_conflict()
        category = Category(name=name, slug=slug)
        try:
            category = await self._catalog.create_category(category)
            await self._catalog.commit()
        except IntegrityError as error:
            if _is_unique_violation(error):
                raise _category_slug_conflict() from error
            raise
        return category

    async def update_category(
        self, category_id: UUID, *, name: str | None = None, slug: str | None = None
    ) -> Category:
        category = await self._require_category(category_id)
        if slug is not None and slug != category.slug:
            if await self._catalog.get_category_by_slug(slug) is not None:
                raise _category_slug_conflict()
            category.slug = slug
        if name is not None:
            category.name = name
        try:
            await self._catalog.commit()
        except IntegrityError as error:
            if _is_unique_violation(error):
                raise _category_slug_conflict() from error
            raise
        return category

    async def delete_category(self, category_id: UUID) -> None:
        category = await self._require_category(category_id)
        if await self._catalog.category_has_products(category.id):
            raise AppError("category_not_empty", "Category contains products", 409)
        await self._catalog.delete_category(category)
        await self._catalog.commit()

    async def create_product(
        self,
        *,
        category_id: UUID,
        name: str,
        slug: str,
        description: str,
        price: Decimal,
        stock_quantity: int,
        is_published: bool,
    ) -> Product:
        await self._require_category(category_id)
        if await self._catalog.get_product_by_slug(slug) is not None:
            raise _product_slug_conflict()
        product = Product(
            category_id=category_id,
            name=name,
            slug=slug,
            description=description,
            price=price,
            stock_quantity=stock_quantity,
            is_published=is_published,
        )
        try:
            product = await self._catalog.create_product(product)
            await self._catalog.commit()
        except IntegrityError as error:
            if _is_unique_violation(error):
                raise _product_slug_conflict() from error
            raise
        return product

    async def update_product(
        self,
        product_id: UUID,
        *,
        category_id: UUID | None = None,
        name: str | None = None,
        slug: str | None = None,
        description: str | None = None,
        price: Decimal | None = None,
        stock_quantity: int | None = None,
        is_published: bool | None = None,
    ) -> Product:
        product = await self._require_product(product_id)
        if category_id is not None:
            await self._require_category(category_id)
            product.category_id = category_id
        if slug is not None and slug != product.slug:
            if await self._catalog.get_product_by_slug(slug) is not None:
                raise _product_slug_conflict()
            product.slug = slug
        if name is not None:
            product.name = name
        if description is not None:
            product.description = description
        if price is not None:
            product.price = price
        if stock_quantity is not None:
            product.stock_quantity = stock_quantity
        if is_published is not None:
            product.is_published = is_published
        try:
            await self._catalog.commit()
        except IntegrityError as error:
            if _is_unique_violation(error):
                raise _product_slug_conflict() from error
            raise
        return product

    async def unpublish_product(self, product_id: UUID) -> Product:
        product = await self._require_product(product_id)
        product.is_published = False
        await self._catalog.commit()
        return product

    async def _require_category(self, category_id: UUID) -> Category:
        category = await self._catalog.get_category(category_id)
        if category is None:
            raise AppError("category_not_found", "Category not found", 404)
        return category

    async def _require_product(self, product_id: UUID) -> Product:
        product = await self._catalog.get_product(product_id)
        if product is None:
            raise AppError("product_not_found", "Product not found", 404)
        return product


def _category_slug_conflict() -> AppError:
    return AppError("category_slug_conflict", "A category with this slug already exists", 409)


def _product_slug_conflict() -> AppError:
    return AppError("product_slug_conflict", "A product with this slug already exists", 409)


def _is_unique_violation(error: IntegrityError) -> bool:
    return getattr(error.orig, "sqlstate", None) == "23505"
