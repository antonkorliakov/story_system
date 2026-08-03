from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.catalog.models import Category, Product


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_category(self, category_id: UUID) -> Category | None:
        return await self._session.get(Category, category_id)

    async def get_category_by_slug(self, slug: str) -> Category | None:
        result = await self._session.execute(select(Category).where(Category.slug == slug))
        return result.scalar_one_or_none()

    async def list_categories(self, limit: int, offset: int) -> tuple[Sequence[Category], int]:
        items_result = await self._session.execute(
            select(Category).order_by(Category.name, Category.id).limit(limit).offset(offset)
        )
        total_result = await self._session.execute(select(func.count()).select_from(Category))
        return items_result.scalars().all(), total_result.scalar_one()

    async def create_category(self, category: Category) -> Category:
        self._session.add(category)
        await self._session.flush()
        return category

    async def delete_category(self, category: Category) -> None:
        await self._session.delete(category)

    async def category_has_products(self, category_id: UUID) -> bool:
        result = await self._session.execute(
            select(func.count()).select_from(Product).where(Product.category_id == category_id)
        )
        return result.scalar_one() > 0

    async def get_product(self, product_id: UUID) -> Product | None:
        return await self._session.get(Product, product_id)

    async def get_published_product(self, product_id: UUID) -> Product | None:
        result = await self._session.execute(
            select(Product).where(Product.id == product_id, Product.is_published.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_product_by_slug(self, slug: str) -> Product | None:
        result = await self._session.execute(select(Product).where(Product.slug == slug))
        return result.scalar_one_or_none()

    async def list_published_products(
        self, category_id: UUID | None, limit: int, offset: int
    ) -> tuple[Sequence[Product], int]:
        conditions: list[ColumnElement[bool]] = [Product.is_published.is_(True)]
        if category_id is not None:
            conditions.append(Product.category_id == category_id)
        items_result = await self._session.execute(
            select(Product)
            .where(*conditions)
            .order_by(Product.created_at.desc(), Product.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total_result = await self._session.execute(
            select(func.count()).select_from(Product).where(*conditions)
        )
        return items_result.scalars().all(), total_result.scalar_one()

    async def create_product(self, product: Product) -> Product:
        self._session.add(product)
        await self._session.flush()
        return product

    async def lock_products(self, product_ids: list[UUID]) -> list[Product]:
        if not product_ids:
            return []
        result = await self._session.execute(
            select(Product)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def commit(self) -> None:
        await self._session.commit()
