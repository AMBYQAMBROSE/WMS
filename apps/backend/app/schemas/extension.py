import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import ClientRequestId, PartnerBrief, PositiveQty, Qty


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- returns ----------


class ReturnInLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None
    # RESTOCK: good condition, restocked into location_id for resale; SCRAP: damaged, recorded only, not stocked
    disposition: Literal["RESTOCK", "SCRAP"]
    location_id: uuid.UUID | None = None
    # Linked original sales order line; matched by item when omitted
    ref_line_id: uuid.UUID | None = None


class ReturnInIn(BaseModel):
    partner_id: uuid.UUID
    ref_document_id: uuid.UUID | None = None
    reason_code_id: uuid.UUID
    remark: str | None = Field(default=None, max_length=400)
    client_request_id: str | None = ClientRequestId
    lines: list[ReturnInLineIn] = Field(min_length=1)


class ReturnOutLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None
    location_id: uuid.UUID


class ReturnOutIn(BaseModel):
    partner_id: uuid.UUID
    ref_document_id: uuid.UUID | None = None
    reason_code_id: uuid.UUID
    remark: str | None = Field(default=None, max_length=400)
    client_request_id: str | None = ClientRequestId
    lines: list[ReturnOutLineIn] = Field(min_length=1)


# ---------- repack ----------


class RepackLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty
    batch_no: str | None = Field(default=None, max_length=50)
    expiry_date: date | None = None
    location_id: uuid.UUID


class RepackIn(BaseModel):
    remark: str | None = Field(default=None, max_length=400)
    client_request_id: str | None = ClientRequestId
    inputs: list[RepackLineIn] = Field(min_length=1)
    outputs: list[RepackLineIn] = Field(min_length=1)


# ---------- returnable assets ----------


class AssetTypeIn(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class AssetTypeRead(_Orm):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool


class AssetTxnIn(BaseModel):
    partner_id: uuid.UUID
    asset_type_id: uuid.UUID
    # ISSUE: lent to the partner (sent with goods); RETURN: returned by the partner
    txn_type: Literal["ISSUE", "RETURN"]
    qty: PositiveQty
    ref_document_id: uuid.UUID | None = None
    remark: str | None = Field(default=None, max_length=400)


class AssetTxnRead(_Orm):
    id: uuid.UUID
    partner: PartnerBrief
    asset_type: AssetTypeRead
    txn_type: Literal["ISSUE", "RETURN"]
    qty_change: Qty
    ref_document_id: uuid.UUID | None
    remark: str | None
    occurred_at: datetime


class AssetBalanceRow(BaseModel):
    partner: PartnerBrief
    asset_type: AssetTypeRead
    outstanding: Qty
