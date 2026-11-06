import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.versioning import ExpectedVersion


class LocationBase(BaseModel):
    code: str
    name: str
    location_type: Literal["WAREHOUSE", "ZONE", "AISLE", "RACK", "BIN", "DOCK"]
    parent_id: uuid.UUID | None = None
    is_pickable: bool = False
    is_locked: bool = False
    capacity_qty: float | None = None
    is_active: bool = True


class LocationCreate(LocationBase):
    pass


class LocationUpdate(ExpectedVersion):
    name: str | None = None
    is_pickable: bool | None = None
    is_locked: bool | None = None
    capacity_qty: float | None = None
    is_active: bool | None = None


class LocationRead(LocationBase):
    row_version: int
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    path: str
