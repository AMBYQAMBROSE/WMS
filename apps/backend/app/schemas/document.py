import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# Quantities are Decimal in the database and JSON would serialize them as strings; convert them to numbers for the frontend
Qty = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
PositiveQty = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=4)]


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PartnerBrief(_Orm):
    id: uuid.UUID
    code: str
    name: str


class UomBrief(_Orm):
    id: uuid.UUID
    code: str
    name: str


class ItemBrief(_Orm):
    id: uuid.UUID
    sku_code: str
    name: str
    is_batch_managed: bool
    is_expiry_managed: bool
    base_uom: UomBrief


class LocationBrief(_Orm):
    id: uuid.UUID
    code: str
    name: str
    location_type: str


class DocumentBrief(_Orm):
    id: uuid.UUID
    doc_type: str
    doc_no: str
    status: str


class DocumentLineRead(_Orm):
    id: uuid.UUID
    line_no: int
    item: ItemBrief
    uom: UomBrief
    qty_planned: Qty
    qty_actual: Qty
    batch_no: str | None
    expiry_date: date | None
    from_location: LocationBrief | None
    to_location: LocationBrief | None
    ref_line_id: uuid.UUID | None


class ReasonBrief(_Orm):
    id: uuid.UUID
    code: str
    name: str


class DocumentSummary(_Orm):
    id: uuid.UUID
    doc_type: str
    doc_no: str
    status: str
    partner: PartnerBrief | None
    ref_document: DocumentBrief | None
    location: LocationBrief | None
    reason_code: ReasonBrief | None
    expected_date: date | None
    posted_at: datetime | None
    remark: str | None
    created_at: datetime


class DocumentRead(DocumentSummary):
    lines: list[DocumentLineRead]


class PurchaseOrderLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty


class PurchaseOrderIn(BaseModel):
    partner_id: uuid.UUID
    expected_date: date | None = None
    remark: str | None = Field(default=None, max_length=400)
    lines: list[PurchaseOrderLineIn] = Field(min_length=1)


class GrnLineIn(BaseModel):
    po_line_id: uuid.UUID
    qty: PositiveQty
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None


ClientRequestId = Field(default=None, min_length=8, max_length=64)


class GrnIn(BaseModel):
    po_id: uuid.UUID
    location_id: uuid.UUID
    remark: str | None = Field(default=None, max_length=400)
    client_request_id: str | None = ClientRequestId
    lines: list[GrnLineIn] = Field(min_length=1)


class TransferLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID


class TransferIn(BaseModel):
    """Shared by putaway and move. A putaway may carry its source goods receipt in ref_document_id; a move does not."""

    ref_document_id: uuid.UUID | None = None
    remark: str | None = Field(default=None, max_length=400)
    client_request_id: str | None = ClientRequestId
    lines: list[TransferLineIn] = Field(min_length=1)


class StockBalanceRead(_Orm):
    id: uuid.UUID
    item: ItemBrief
    location: LocationBrief
    batch_no: str | None
    expiry_date: date | None
    qty_on_hand: Qty
    qty_allocated: Qty


class LedgerRefLine(_Orm):
    id: uuid.UUID
    document: DocumentBrief


class StockLedgerRead(_Orm):
    id: uuid.UUID
    item: ItemBrief
    location: LocationBrief
    batch_no: str | None
    expiry_date: date | None
    qty_change: Qty
    movement_type: str
    ref_line: LedgerRefLine | None
    occurred_at: datetime


# ---------- reason codes ----------


class ReasonCodeIn(BaseModel):
    category: str = Field(default="ADJUST", max_length=30)
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    external_code: str | None = Field(default=None, max_length=50)
    is_active: bool = True


class ReasonCodeRead(_Orm):
    id: uuid.UUID
    category: str
    code: str
    name: str
    external_code: str | None
    is_active: bool


# ---------- stock adjustments ----------

SignedQty = Annotated[Decimal, Field(max_digits=18, decimal_places=4)]


class AdjustmentLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    location_id: uuid.UUID
    # Positive increases, negative decreases; changing expiry uses two lines: decrease the old expiry, increase the new one
    qty: SignedQty
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None


class AdjustmentIn(BaseModel):
    reason_code_id: uuid.UUID
    remark: str | None = Field(default=None, max_length=400)
    client_request_id: str | None = ClientRequestId
    lines: list[AdjustmentLineIn] = Field(min_length=1)


# ---------- cycle counts ----------


class CycleCountCreate(BaseModel):
    location_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    remark: str | None = Field(default=None, max_length=400)


class CountEntryIn(BaseModel):
    """One count entry: total counted quantity of this item (batch/expiry) at this location. "Set" rather than "add" semantics, so resubmitting gives the same result."""

    location_id: uuid.UUID
    item_id: uuid.UUID
    uom_id: uuid.UUID | None = None
    qty: Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None


class RecountIn(BaseModel):
    line_ids: list[uuid.UUID] = Field(min_length=1)


class UserBrief(_Orm):
    id: uuid.UUID
    username: str
    display_name: str


class CountEntryRead(_Orm):
    round: int
    qty: Qty
    counter: UserBrief
    counted_at: datetime


class CountLineRead(_Orm):
    id: uuid.UUID
    line_no: int
    item: ItemBrief
    uom: UomBrief
    # Book quantity (snapshot at creation); null without the cycle_count.view_expected permission (blind count)
    qty_planned: Qty | None
    qty_actual: Qty
    # The API field stays counted_at (already used by the PDA/frontend); it maps to the model's generic confirmed_at
    counted_at: datetime | None = Field(validation_alias="confirmed_at")
    batch_no: str | None
    expiry_date: date | None
    to_location: LocationBrief | None
    count_entries: list[CountEntryRead]


class CountLocationRead(_Orm):
    location: LocationBrief


class CountRead(DocumentSummary):
    count_locations: list[CountLocationRead]
    lines: list[CountLineRead]
