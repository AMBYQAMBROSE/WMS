import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

from app.schemas.document import ItemBrief, PartnerBrief, Price, Qty, UomBrief

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


class StockAlertRow(BaseModel):
    item: ItemBrief
    # out: nothing available; below: under the minimum stock (alarm); low: within 25% above it (warning)
    level: str
    min_stock_qty: Qty
    available: Qty
    on_hand: Qty
    shortfall: Qty


class StockAlerts(BaseModel):
    """Items under their stock buffer (Item.min_stock_qty), most urgent first; rows holds the first 50"""

    alarm_count: int
    out_count: int
    warning_count: int
    rows: list[StockAlertRow]


class Dashboard(BaseModel):
    date: date
    today: TodayStats
    backlog: Backlog
    stock: StockStats
    trend: list[DailyFlow]
    stock_alerts: StockAlerts


# ---------------------------------------------------------------- trend analysis (GET /reports/analytics)


class PeriodRange(BaseModel):
    start: date
    # Inclusive
    end: date


class AnalyticsPeriods(BaseModel):
    """mtd / ytd: this month and year to date; *_ly: the same dates a year earlier; three_years: the three full years before this one"""

    mtd: PeriodRange
    mtd_ly: PeriodRange
    ytd: PeriodRange
    ytd_ly: PeriodRange
    last_year: PeriodRange
    three_years: PeriodRange


class MonthPoint(BaseModel):
    month: str  # YYYY-MM
    purchased_qty: Qty
    loss_qty: Qty
    # Null without cost.view; loss value is at average purchase cost
    purchased_value: Price = None
    loss_value: Price = None


class PackingUnit(BaseModel):
    uom: UomBrief
    factor: Qty


class ItemTrendRow(BaseModel):
    """Base-unit quantities per period for one SKU; packing is its largest packing unit, for showing them in cartons/bales"""

    item: ItemBrief
    packing: PackingUnit | None
    mtd: Qty
    mtd_ly: Qty
    ytd: Qty
    ytd_ly: Qty
    last_year: Qty
    # Average per year over the three full years before this one
    avg_3y: Qty
    ytd_value: Price = None
    ytd_ly_value: Price = None


class ItemTrendPage(BaseModel):
    total: int
    rows: list[ItemTrendRow]


class SupplierRow(BaseModel):
    partner: PartnerBrief
    credit_terms_days: int | None
    ytd_qty: Qty
    ytd_value: Price = None
    ytd_ly_value: Price = None
    # Share of this year's purchase value
    share_pct: Ratio | None = None
    receipts: int
    outstanding: Price = None
    overdue: Price = None
    open_receipts: int
    overdue_receipts: int
    # Over receipts settled in the last 12 months
    avg_days_to_settle: Ratio | None
    on_time_pct: Ratio | None


class SupplierSummary(BaseModel):
    rows: list[SupplierRow]
    outstanding: Price = None
    overdue: Price = None
    open_receipts: int
    overdue_receipts: int


class PeriodTotals(BaseModel):
    """All SKUs together per period, in base units; *_value at purchase price (losses: average cost), null without cost.view"""

    mtd: Qty
    mtd_ly: Qty
    ytd: Qty
    ytd_ly: Qty
    last_year: Qty
    avg_3y: Qty
    mtd_value: Price = None
    mtd_ly_value: Price = None
    ytd_value: Price = None
    ytd_ly_value: Price = None
    last_year_value: Price = None
    avg_3y_value: Price = None


class AnalyticsTotals(BaseModel):
    purchases: PeriodTotals
    losses: PeriodTotals


class Analytics(BaseModel):
    date: date
    periods: AnalyticsPeriods
    months: list[MonthPoint]
    totals: AnalyticsTotals
    purchases: ItemTrendPage
    losses: ItemTrendPage
    suppliers: SupplierSummary


class PricePoint(BaseModel):
    month: str
    # Weighted average cost per base unit of the month's priced receipts; null in months without any
    avg_cost: Price = None
    qty: Qty


class PricingRow(BaseModel):
    item: ItemBrief
    latest_cost: Price = None
    latest_at: datetime | None
    avg_cost_ytd: Price = None
    # Average cost in the latest month with receipts that is at least 12 months back
    cost_year_ago: Price = None
    change_pct: Ratio | None
    min_cost: Price = None
    max_cost: Price = None
    points: list[PricePoint]


class Pricing(BaseModel):
    months: list[str]
    rows: list[PricingRow]


# ---------------------------------------------------------------- supplier payables


class PayableRow(BaseModel):
    id: uuid.UUID
    doc_no: str
    partner: PartnerBrief
    posted_at: datetime
    payment_due_date: date
    settled_on: date | None
    credit_terms_days: int | None
    value: Price = None
    # Positive: days past due (open receipts), or days paid late (settled ones)
    days_overdue: int
    status: str  # open / overdue / settled


class PayablePage(BaseModel):
    total: int
    outstanding: Price = None
    overdue: Price = None
    rows: list[PayableRow]


class SettleIn(BaseModel):
    settled_on: date


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
