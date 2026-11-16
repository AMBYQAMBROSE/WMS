"""Warehouse map (live bin view and activity playback), batch traceability and recalls."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.document import DocumentBrief, DocumentRead, ItemBrief, LocationBrief, PartnerBrief, Qty


# ------------------------------------------------------------------ warehouse map


class MapWarehouse(BaseModel):
    id: uuid.UUID
    code: str
    name: str


class MapNode(BaseModel):
    """One location of the warehouse tree; containers (zone, aisle, rack) carry no stock of their own"""

    id: uuid.UUID
    parent_id: uuid.UUID | None
    code: str
    name: str
    location_type: str
    is_pickable: bool
    is_locked: bool
    # Inside a running cycle count: stock movements are paused
    is_counting: bool
    capacity_qty: Qty | None
    qty_on_hand: Qty
    qty_allocated: Qty
    sku_count: int
    # Earliest expiry of the stock held here (null: nothing with an expiry date)
    nearest_expiry: date | None
    # Holds a batch under an active recall
    has_recalled: bool
    # Pick lines taken from this bin in the last PICK_WINDOW_DAYS days
    picks: int


class WarehouseMap(BaseModel):
    warehouses: list[MapWarehouse]
    warehouse: MapWarehouse | None
    nodes: list[MapNode]
    pick_window_days: int
    generated_at: datetime


class MapActivity(BaseModel):
    """Something that happened at a location: a stock movement, or a line confirmed on a PDA (pick, put, count)"""

    at: datetime
    location_id: uuid.UUID
    kind: str  # MOVEMENT | SCAN
    movement_type: str | None
    doc_type: str | None
    doc_no: str | None
    document_id: uuid.UUID | None
    sku_code: str
    qty: Qty | None
    user_id: uuid.UUID | None
    user_name: str | None


class MapActivityPage(BaseModel):
    since: datetime
    until: datetime
    truncated: bool
    events: list[MapActivity]


class MapBinStock(BaseModel):
    item: ItemBrief
    batch_no: str | None
    expiry_date: date | None
    qty_on_hand: Qty
    qty_allocated: Qty
    recall: DocumentBrief | None


class MapBinDetail(BaseModel):
    location: LocationBrief
    path: str
    is_locked: bool
    is_counting: bool
    counting_doc: DocumentBrief | None
    capacity_qty: Qty | None
    stock: list[MapBinStock]
    recent: list[MapActivity]


# ------------------------------------------------------------------ traceability


class BatchHit(BaseModel):
    item: ItemBrief
    batch_no: str
    first_seen: datetime
    last_seen: datetime
    qty_on_hand: Qty
    recalled: bool


class TracePartner(PartnerBrief):
    contact_name: str | None = None
    contact_phone: str | None = None
    address: str | None = None


class TraceFlow(BaseModel):
    """Quantity of the batch that one document brought in or took out"""

    # Null only for stock booked without a document (none of today's flows do that)
    document: DocumentBrief | None
    # The document this one was made from: the purchase order of a receipt, the sales order of a shipment
    source: DocumentBrief | None
    partner: TracePartner | None
    # RECEIVE, RETURN_IN, REPACK_IN, ADJUST_IN, COUNT_GAIN / SHIP_OUT, RETURN_OUT, REPACK_OUT, ADJUST_OUT, COUNT_LOSS
    movement_type: str
    qty: Qty
    at: datetime
    vehicle_no: str | None = None
    driver_name: str | None = None


class TraceStock(BaseModel):
    location: LocationBrief
    expiry_date: date | None
    qty_on_hand: Qty
    qty_allocated: Qty


class TraceMovement(BaseModel):
    at: datetime
    movement_type: str
    qty: Qty
    location: LocationBrief
    document: DocumentBrief | None
    user_name: str | None


class TraceSummary(BaseModel):
    received: Qty
    returned_in: Qty
    other_in: Qty
    shipped: Qty
    returned_out: Qty
    other_out: Qty
    qty_on_hand: Qty
    qty_allocated: Qty
    customers: int
    shipments: int
    suppliers: int


class BatchTrace(BaseModel):
    item: ItemBrief
    batch_no: str
    expiry_dates: list[date]
    summary: TraceSummary
    inbound: list[TraceFlow]
    outbound: list[TraceFlow]
    stock: list[TraceStock]
    # Unposted shipments that would send this batch out (a recall stops them from being posted)
    pending_shipments: list[TraceFlow]
    movements: list[TraceMovement]
    movements_total: int
    recalls: list[DocumentBrief]
    active_recall: DocumentBrief | None


class DocumentBatch(BaseModel):
    """A batch on a document, with where it came from and where else it went"""

    item: ItemBrief
    batch_no: str | None
    expiry_date: date | None
    qty: Qty
    suppliers: list[PartnerBrief]
    receipts: list[DocumentBrief]
    other_customers: int
    qty_on_hand: Qty
    active_recall: DocumentBrief | None


class DocumentTrace(BaseModel):
    document: DocumentBrief
    partner: PartnerBrief | None
    posted_at: datetime | None
    batches: list[DocumentBatch]


# ------------------------------------------------------------------ recalls


class RecallIn(BaseModel):
    item_id: uuid.UUID
    batch_no: str = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=1, max_length=400)
    # Bin or dock the recalled stock is moved to; a draft move is made for everything that can be moved there now
    quarantine_location_id: uuid.UUID | None = None
    client_request_id: str | None = Field(default=None, max_length=64)


class RecallSkipped(BaseModel):
    location: LocationBrief
    qty: Qty
    reason: str


class RecallRead(BaseModel):
    document: DocumentRead
    moves: list[DocumentBrief]
    # Stock of the batch the quarantine move could not include, and why (allocated, locked, being counted)
    skipped: list[RecallSkipped]
    trace: BatchTrace
