import uuid

from pydantic import BaseModel, ConfigDict


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
    pass


class ItemUpdate(BaseModel):
    name: str | None = None
    barcode: str | None = None
    category: str | None = None
    is_batch_managed: bool | None = None
    is_expiry_managed: bool | None = None
    is_serial_managed: bool | None = None
    shelf_life_days: int | None = None
    is_active: bool | None = None


class ItemRead(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
