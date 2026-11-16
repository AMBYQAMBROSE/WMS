import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import (
    ClientRequestId,
    DocumentLineRead,
    DocumentRead,
    DocumentSummary,
    ItemBrief,
    PositiveQty,
    Qty,
    UomBrief,
    UserBrief,
)
from app.schemas.versioning import ExpectedVersion


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- sales orders ----------


class SalesOrderLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty


class SalesOrderIn(ExpectedVersion):
    partner_id: uuid.UUID
    expected_date: date | None = None
    remark: str | None = Field(default=None, max_length=400)
    lines: list[SalesOrderLineIn] = Field(min_length=1)


class SalesOrderLineRead(BaseModel):
    """Order line with fulfilment progress. Progress quantities are base units (base_uom); the ordered quantity is in the order unit (uom)"""

    id: uuid.UUID
    line_no: int
    item: ItemBrief
    uom: UomBrief
    qty_planned: Qty
    ordered_base: Qty
    allocated: Qty
    picked: Qty
    shipped: Qty
    unallocated: Qty
    # Posted customer returns (base units) linked to this order line
    returned: Qty


class SalesOrderRead(DocumentSummary):
    lines: list[SalesOrderLineRead]


class AllocateIn(BaseModel):
    staging_location_id: uuid.UUID
    # Cross-docking (requires CROSS_DOCK): allocate only from this receiving dock (DOCK); goods go to staging without putaway
    source_location_id: uuid.UUID | None = None


class ShortageRead(BaseModel):
    line_id: uuid.UUID
    sku_code: str
    name: str
    qty: Qty
    uom_code: str


# ---------- picks ----------


class PickLineRead(DocumentLineRead):
    confirmed_at: datetime | None
    confirmer: UserBrief | None


class PickRead(DocumentSummary):
    lines: list[PickLineRead]


class AllocationResult(BaseModel):
    pick: PickRead
    shortages: list[ShortageRead]


class PickConfirmIn(BaseModel):
    """Picked quantity (base units). "Set" semantics: resubmitting gives the same result, so PDA offline resends are safe"""

    qty: Qty = Field(ge=0)


# ---------- shipments ----------


class ShipmentInfoIn(BaseModel):
    carrier: str | None = Field(default=None, max_length=100)
    vehicle_no: str | None = Field(default=None, max_length=30)
    driver_name: str | None = Field(default=None, max_length=50)
    driver_phone: str | None = Field(default=None, max_length=30)
    seal_no: str | None = Field(default=None, max_length=50)


class ShipmentInfoUpdate(ShipmentInfoIn, ExpectedVersion):
    pass


class ShipmentCreate(ShipmentInfoIn):
    so_id: uuid.UUID
    client_request_id: str | None = ClientRequestId


class ShipmentInfoRead(_Orm):
    carrier: str | None
    vehicle_no: str | None
    driver_name: str | None
    driver_phone: str | None
    seal_no: str | None


class ShipmentRead(DocumentRead):
    shipment_info: ShipmentInfoRead | None


class ShipmentCheckIn(BaseModel):
    """Scanned quantity of a shipment line so far (base units). "Set" semantics: a resend gives the same result"""

    qty: Qty = Field(ge=0)


class LoadingHistory(BaseModel):
    """Recently used loading details, for choosing instead of typing"""

    carriers: list[str]
    vehicles: list[ShipmentInfoRead]


# ---------- shortage report ----------


class ShortageReportRow(BaseModel):
    so_id: uuid.UUID
    so_doc_no: str
    customer: str
    expected_date: date | None
    line_id: uuid.UUID
    item: ItemBrief
    ordered: Qty
    unallocated: Qty
    # Quantity of this item currently allocatable warehouse-wide: > 0 means re-allocating would cover it, 0 means replenish/purchase
    available: Qty
