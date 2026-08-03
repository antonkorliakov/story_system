from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CartItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    quantity: int = Field(ge=1)


class CartItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1)


class CartItemResponse(BaseModel):
    id: UUID
    product_id: UUID
    name: str
    unit_price: Decimal
    quantity: int
    line_total: Decimal


class CartResponse(BaseModel):
    items: list[CartItemResponse]
    total: Decimal
