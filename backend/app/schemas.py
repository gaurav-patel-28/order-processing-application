from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=36)]
Cents = Annotated[int, Field(ge=0, le=100_000_000, strict=True)]
Stock = Annotated[int, Field(ge=0, le=1_000_000, strict=True)]


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Login(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UserOut(Output):
    id: str
    org_id: str
    email: str
    role: str


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=64, pattern=r"\S")
    name: str = Field(min_length=1, max_length=160, pattern=r"\S")
    price_cents: Cents
    available: Stock = 0
    active: bool = True


class ProductEdit(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=64, pattern=r"\S")
    name: str | None = Field(default=None, min_length=1, max_length=160, pattern=r"\S")
    price_cents: Cents | None = None
    active: bool | None = None
    available: Stock | None = None

    @model_validator(mode="after")
    def no_nulls(self):
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Explicit null fields are not allowed")
        return self


class InventoryEdit(BaseModel):
    available: Stock


class ProductOut(Output):
    id: str
    org_id: str
    sku: str
    name: str
    price_cents: int
    active: bool
    available: int
    reserved: int
    sold: int


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: Identifier
    quantity: int = Field(ge=1, le=1000, strict=True)


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Item] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_products(self):
        if len({item.product_id for item in self.items}) != len(self.items):
            raise ValueError("Combine repeated products into one line")
        return self


class LineOut(Output):
    product_id: str
    name: str
    quantity: int
    unit_price_cents: int


class EventOut(Output):
    id: str
    kind: str
    actor: str
    details: dict
    created_at: datetime


class OrderOut(Output):
    id: str
    org_id: str
    customer_id: str
    status: str
    subtotal_cents: int
    discount_cents: int
    tax_cents: int
    total_cents: int
    created_at: datetime
    lines: list[LineOut]
    events: list[EventOut]


class AttemptOut(Output):
    id: str
    order_id: str
    provider_id: str
    amount_cents: int
    status: str


class RefundOut(Output):
    id: str
    order_id: str
    provider_id: str
    amount_cents: int


class Simulate(BaseModel):
    outcome: Literal["success", "failure"]


class Webhook(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=128)
    provider_id: str = Field(min_length=1, max_length=100)
    outcome: Literal["success", "failure"]
    amount_cents: int = Field(ge=0, le=100_000_000_000_000, strict=True)
    currency: Literal["USD"]
