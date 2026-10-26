import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

# 数量在库里是 Decimal，JSON 默认会序列化成字符串，这里统一转成数字方便前端
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


class DocumentSummary(_Orm):
    id: uuid.UUID
    doc_type: str
    doc_no: str
    status: str
    partner: PartnerBrief | None
    ref_document: DocumentBrief | None
    location: LocationBrief | None
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


class GrnIn(BaseModel):
    po_id: uuid.UUID
    location_id: uuid.UUID
    remark: str | None = Field(default=None, max_length=400)
    lines: list[GrnLineIn] = Field(min_length=1)


class PutawayLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID


class PutawayIn(BaseModel):
    ref_document_id: uuid.UUID | None = None
    remark: str | None = Field(default=None, max_length=400)
    lines: list[PutawayLineIn] = Field(min_length=1)


class StockBalanceRead(_Orm):
    id: uuid.UUID
    item: ItemBrief
    location: LocationBrief
    batch_no: str | None
    expiry_date: date | None
    qty_on_hand: Qty


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
