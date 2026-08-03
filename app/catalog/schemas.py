from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class CategoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=SLUG_PATTERN)


class CategoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255, pattern=SLUG_PATTERN)


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class CategoryListResponse(BaseModel):
    items: list[CategoryResponse]
    limit: int
    offset: int
    total: int


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=SLUG_PATTERN)
    description: str = ""
    price: Decimal = Field(ge=Decimal(0), max_digits=12, decimal_places=2)
    stock_quantity: int = Field(ge=0)
    is_published: bool = False


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255, pattern=SLUG_PATTERN)
    description: str | None = None
    price: Decimal | None = Field(default=None, ge=Decimal(0), max_digits=12, decimal_places=2)
    stock_quantity: int | None = Field(default=None, ge=0)
    is_published: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    name: str
    slug: str
    description: str
    price: Decimal
    stock_quantity: int
    is_published: bool
    created_at: datetime
    updated_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    limit: int
    offset: int
    total: int
