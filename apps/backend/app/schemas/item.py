import uuid
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import Qty, UomBrief
from app.schemas.versioning import ExpectedVersion

MAX_PACKINGS = 10


class ItemPackingIn(BaseModel):
    """A packing unit of the item: one `uom_id` (carton, pallet...) holds `factor` base units"""

    uom_id: uuid.UUID
    factor: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]


class ItemPackingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uom: UomBrief = Field(validation_alias="from_uom")
    factor: Qty


class ItemBase(BaseModel):
    sku_code: str
    name: str
    barcode: str | None = None
    category: str | None = None
    base_uom_id: uuid.UUID
    is_batch_managed: bool = False
    is_expiry_managed: bool = False
    is_serial_managed: bool = False
    shelf_life_days: int | None = None
    is_active: bool = True


class ItemCreate(ItemBase):
    packings: list[ItemPackingIn] = Field(default_factory=list, max_length=MAX_PACKINGS)


class ItemUpdate(ExpectedVersion):
    name: str | None = None
    barcode: str | None = None
    category: str | None = None
    is_batch_managed: bool | None = None
    is_expiry_managed: bool | None = None
    is_serial_managed: bool | None = None
    shelf_life_days: int | None = None
    is_active: bool | None = None
    # The full list of packing units; omitted (or null) leaves them as they are
    packings: list[ItemPackingIn] | None = Field(default=None, max_length=MAX_PACKINGS)


class ItemRead(ItemBase):
    row_version: int
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    packings: list[ItemPackingRead] = []
