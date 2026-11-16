import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.schemas.document import PartnerBrief, Qty, UomBrief
from app.schemas.outbound import SalesOrderLineIn


class CartUom(UomBrief):
    """A unit the item can be ordered in; factor = base units per one of this unit (1 for the base unit)"""

    factor: Qty


class CatalogItem(BaseModel):
    id: uuid.UUID
    sku_code: str
    name: str
    category: str | None
    barcode: str | None
    base_uom: UomBrief
    uoms: list[CartUom]
    # Indicative stock available to promise, in base units: on hand minus allocated in usable bins (active, unlocked,
    # not expired). Ordering more is allowed; the shortfall shows up at allocation.
    available: Qty


class CatalogPage(BaseModel):
    items: list[CatalogItem]
    total: int
    categories: list[str]


class CartOrderIn(BaseModel):
    """Submit the cart. A customer account may leave partner_id empty (its own customer is used) and cannot order for another."""

    partner_id: uuid.UUID | None = None
    expected_date: date | None = None
    remark: str | None = Field(default=None, max_length=400)
    lines: list[SalesOrderLineIn] = Field(min_length=1, max_length=500)


class CartContext(BaseModel):
    """Who the cart orders for: fixed for a customer account, chosen per order by internal staff"""

    partner: PartnerBrief | None
