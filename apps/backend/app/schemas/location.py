import uuid

from pydantic import BaseModel, ConfigDict


class LocationBase(BaseModel):
    code: str
    name: str
    location_type: str  # WAREHOUSE / ZONE / AISLE / RACK / BIN
    parent_id: uuid.UUID | None = None
    is_pickable: bool = False
    is_locked: bool = False
    capacity_qty: float | None = None
    is_active: bool = True


class LocationCreate(LocationBase):
    pass


class LocationUpdate(BaseModel):
    name: str | None = None
    is_pickable: bool | None = None
    is_locked: bool | None = None
    capacity_qty: float | None = None
    is_active: bool | None = None


class LocationRead(LocationBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    path: str
