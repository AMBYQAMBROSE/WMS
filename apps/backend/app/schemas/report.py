import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.schemas.document import ItemBrief, PartnerBrief, Qty

# Ratios such as turnover and fill rate are also output as numbers
Ratio = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class _Row(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TodayStats(BaseModel):
    received_qty: Qty
    shipped_qty: Qty
    grn_posted: int
    shipments_posted: int


class Backlog(BaseModel):
    po_open: int
    grn_draft: int
    putaway_draft: int
    so_open: int
    pick_open: int
    shipment_draft: int
    count_open: int
    shortage_lines: int


class StockStats(BaseModel):
    sku_count: int
    qty_on_hand: Qty
    qty_allocated: Qty
    bins_total: int
    bins_used: int
    expired_qty: Qty
    expiring_30d_qty: Qty


class DailyFlow(BaseModel):
    date: date
    received_qty: Qty
    shipped_qty: Qty


class Dashboard(BaseModel):
    date: date
    today: TodayStats
    backlog: Backlog
    stock: StockStats
    trend: list[DailyFlow]


class TurnoverRow(_Row):
    item: ItemBrief
    opening: Qty
    received: Qty
    shipped: Qty
    other: Qty
    closing: Qty
    average: Qty
    turnover: Ratio | None
    days_on_hand: Ratio | None


class PickerKpiRow(_Row):
    user_id: uuid.UUID
    username: str
    display_name: str
    picks: int
    lines: int
    qty: Qty
    short_lines: int
    fill_rate: Ratio | None
    first_at: datetime
    last_at: datetime


class ExpiryRow(_Row):
    item: ItemBrief
    location_code: str
    batch_no: str | None
    expiry_date: date
    days_left: int
    qty_on_hand: Qty
    qty_allocated: Qty


class PartnerLedgerRow(_Row):
    partner: PartnerBrief
    item: ItemBrief
    received: Qty
    returned_to_supplier: Qty
    shipped: Qty
    returned_by_customer: Qty
    documents: int


# Report paging: total is the number of rows, rows holds the first `limit`; full data via format=csv
class TurnoverPage(BaseModel):
    total: int
    rows: list[TurnoverRow]


class PickerKpiPage(BaseModel):
    total: int
    rows: list[PickerKpiRow]


class ExpiryPage(BaseModel):
    total: int
    rows: list[ExpiryRow]


class PartnerLedgerPage(BaseModel):
    total: int
    rows: list[PartnerLedgerRow]


class OccupancyArea(BaseModel):
    """Bins grouped by their zone (or by warehouse for bins not under a zone)"""

    id: uuid.UUID
    code: str
    name: str
    location_type: str
    warehouse_code: str
    bins_total: int
    # Bins holding any stock
    bins_used: int
    # Bins locked for use (location master data)
    bins_locked: int
    qty_on_hand: Qty
    # Sum of capacity_qty over bins that have one; null when no bin in the area has a capacity
    capacity_qty: Qty | None
