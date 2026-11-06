import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.versioning import ExpectedVersion

PartnerType = Literal["customer", "supplier", "both"]


class BusinessPartnerBase(BaseModel):
    code: str
    name: str
    partner_type: PartnerType
    contact_name: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    is_active: bool = True


class BusinessPartnerCreate(BusinessPartnerBase):
    pass


class BusinessPartnerUpdate(ExpectedVersion):
    name: str | None = None
    partner_type: PartnerType | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    is_active: bool | None = None


class BusinessPartnerRead(BusinessPartnerBase):
    row_version: int
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
