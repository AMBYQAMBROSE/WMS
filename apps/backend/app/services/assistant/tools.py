"""Read-only tools the AI assistant may call. Each one wraps an existing service, runs with the signed-in user's
tenant, and is offered to the model only when the user holds its permission (and checked again when it runs), so the
assistant can never see more than the user could on screen, and can change nothing.

Results are compact JSON: quantities as numbers in base units, records named by their codes, at most MAX_ROWS rows
with a note when there were more, so the model knows it saw only part of the data.
"""

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader
from app.models.item import Item, ItemBarcode
from app.models.location import Location
from app.services import stock_service
from app.services.document_common import list_documents
from app.services.item_service import ItemService
from app.services.report_service import ReportService, to_utc, today_local
from app.services.sales_order_service import SalesOrderService

MAX_ROWS = 50

# Document type -> permission needed to read it, and the plain name the model and the user see
DOCUMENT_TYPES: dict[str, tuple[str, str]] = {
    "PO": ("purchase_order.read", "purchase order"),
    "GRN": ("grn.read", "goods receipt"),
    "PUTAWAY": ("putaway.read", "putaway"),
    "MOVE": ("move.read", "move"),
    "ADJUST": ("adjustment.read", "stock adjustment"),
    "COUNT": ("cycle_count.read", "cycle count"),
    "SO": ("sales_order.read", "sales order"),
    "PICK": ("pick.read", "pick list"),
    "SHIP": ("shipment.read", "shipment"),
    "RETURN_IN": ("return_in.read", "customer return"),
    "RETURN_OUT": ("return_out.read", "return to supplier"),
    "REPACK": ("repack.read", "repack"),
}
DocType = Literal["PO", "GRN", "PUTAWAY", "MOVE", "ADJUST", "COUNT", "SO", "PICK", "SHIP", "RETURN_IN", "RETURN_OUT", "REPACK"]


class ToolError(Exception):
    """A problem the model can act on (unknown SKU, no permission, ...): returned to it as an error result"""


@dataclass
class ToolContext:
    db: Session
    tenant_id: uuid.UUID
    permissions: set[str]

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise ToolError(f"The user is not allowed to see this (needs permission {permission})")


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    # Offered when the user holds any of these
    permissions: tuple[str, ...]
    run: Callable[[ToolContext, Any], Any]

    def definition(self) -> dict:
        schema = self.input_model.model_json_schema()
        _strip_titles(schema)
        # Inputs stream as they are generated (the agent streams every request); they are validated before running
        return {"name": self.name, "description": self.description, "input_schema": schema, "eager_input_streaming": True}

    def offered_to(self, permissions: set[str]) -> bool:
        return any(p in permissions for p in self.permissions)

    def execute(self, ctx: ToolContext, raw_input: Any) -> str:
        try:
            args = self.input_model.model_validate(raw_input)
        except ValidationError as exc:
            raise ToolError(f"Invalid input: {exc.errors(include_url=False)}") from exc
        if not self.offered_to(ctx.permissions):
            raise ToolError("The user is not allowed to use this tool")
        return json.dumps(_plain(self.run(ctx, args)), ensure_ascii=False, separators=(",", ":"))


def _strip_titles(schema: Any) -> None:
    """Pydantic adds a title to every field; they only cost tokens"""
    if isinstance(schema, dict):
        schema.pop("title", None)
        for value in schema.values():
            _strip_titles(value)
    elif isinstance(schema, list):
        for value in schema:
            _strip_titles(value)


def _plain(value: Any) -> Any:
    """Service results to JSON: numbers, ISO dates, and records reduced to the codes people know them by"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Item):
        return {"sku": value.sku_code, "name": value.name}
    if isinstance(value, Location):
        return value.code
    if isinstance(value, BusinessPartner):
        return {"code": value.code, "name": value.name}
    if isinstance(value, BaseModel):
        return _plain(value.model_dump())
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items() if not str(k).endswith("_id") and k != "id"}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def _rows(rows: list, total: int | None = None) -> dict:
    total = len(rows) if total is None else total
    result = {"rows": rows[:MAX_ROWS], "total_rows": total}
    if total > MAX_ROWS:
        result["note"] = f"Only the first {MAX_ROWS} of {total} rows are shown; ask the user to narrow the question"
    return result


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- lookups shared by tools


def _item(ctx: ToolContext, sku_or_barcode: str) -> Item:
    code = sku_or_barcode.strip()
    item = ctx.db.scalar(
        select(Item).where(Item.tenant_id == ctx.tenant_id, Item.sku_code == code, Item.is_deleted == false())
    ) or ctx.db.scalar(
        select(Item)
        .join(ItemBarcode, ItemBarcode.item_id == Item.id)
        .where(Item.tenant_id == ctx.tenant_id, ItemBarcode.barcode == code, Item.is_deleted == false())
    )
    if item is None:
        raise ToolError(f"No item with SKU or barcode {code!r}; use find_items to search by name")
    return item


def _location(ctx: ToolContext, code: str) -> Location:
    location = ctx.db.scalar(
        select(Location).where(
            Location.tenant_id == ctx.tenant_id, Location.code == code.strip(), Location.is_deleted == false()
        )
    )
    if location is None:
        raise ToolError(f"No location with code {code!r}")
    return location


# ---------------------------------------------------------------- tools


class FindItemsIn(_In):
    keyword: str = Field(min_length=1, max_length=100, description="Part of the SKU or name, or an exact barcode")


def find_items(ctx: ToolContext, args: FindItemsIn) -> dict:
    items = ItemService(ctx.db).list(ctx.tenant_id, 0, MAX_ROWS + 1, args.keyword)
    rows = [
        {"sku": i.sku_code, "name": i.name, "barcode": i.barcode, "category": i.category, "active": i.is_active,
         "batch_managed": i.is_batch_managed, "expiry_managed": i.is_expiry_managed}
        for i in items
    ]
    return _rows(rows)


class StockOnHandIn(_In):
    sku: str | None = Field(default=None, description="SKU or barcode of one item")
    location_code: str | None = Field(default=None, description="Code of one location (stock directly at it)")


def stock_on_hand(ctx: ToolContext, args: StockOnHandIn) -> dict:
    if not args.sku and not args.location_code:
        raise ToolError("Give a SKU, a location code, or both")
    item = _item(ctx, args.sku) if args.sku else None
    location = _location(ctx, args.location_code) if args.location_code else None
    balances = stock_service.list_balances(
        ctx.db, ctx.tenant_id, item.id if item else None, location.id if location else None, 0, 500
    )
    rows = [
        {"sku": b.item.sku_code, "item": b.item.name, "location": b.location.code, "batch_no": b.batch_no,
         "expiry_date": b.expiry_date, "on_hand": b.qty_on_hand, "allocated": b.qty_allocated,
         "available": b.qty_on_hand - b.qty_allocated}
        for b in balances
        if b.qty_on_hand
    ]
    result = _rows(rows)
    result["total_on_hand"] = float(sum(Decimal(str(r["on_hand"])) for r in rows))
    return result


class StockMovementsIn(_In):
    sku: str = Field(description="SKU or barcode of the item")
    days: int = Field(default=30, ge=1, le=366, description="How many days back, counting today")
    location_code: str | None = Field(default=None, description="Only movements at this location")


def stock_movements(ctx: ToolContext, args: StockMovementsIn) -> dict:
    item = _item(ctx, args.sku)
    location = _location(ctx, args.location_code) if args.location_code else None
    since = to_utc(today_local() - timedelta(days=args.days - 1))
    entries = stock_service.list_ledger(ctx.db, ctx.tenant_id, item.id, location.id if location else None, 0, 500)
    rows = [
        {"at": e.occurred_at, "location": e.location.code, "movement": e.movement_type, "qty_change": e.qty_change,
         "batch_no": e.batch_no, "document": e.ref_line.document.doc_no if e.ref_line else None}
        for e in entries
        if e.occurred_at >= since
    ]
    return {"sku": item.sku_code, "item": item.name, "times_are": "UTC", **_rows(rows)}


class ListDocumentsIn(_In):
    doc_type: DocType = Field(description="PO purchase order, GRN goods receipt, PUTAWAY, MOVE, ADJUST stock adjustment, "
                              "COUNT cycle count, SO sales order, PICK pick list, SHIP shipment, RETURN_IN customer "
                              "return, RETURN_OUT return to supplier, REPACK")
    status: str | None = Field(default=None, description="e.g. DRAFT, CONFIRMED, POSTED, CANCELLED, SHIPPED, OPEN")
    keyword: str | None = Field(default=None, max_length=100,
                                description="Part of the document number, source document number, partner or remark")
    created_from: date | None = Field(default=None, description="First creation day, inclusive")
    created_to: date | None = Field(default=None, description="Last creation day, inclusive")


def list_documents_tool(ctx: ToolContext, args: ListDocumentsIn) -> dict:
    permission, _ = DOCUMENT_TYPES[args.doc_type]
    ctx.require(permission)
    docs = list_documents(
        ctx.db, ctx.tenant_id, args.doc_type, status=args.status or None, keyword=args.keyword,
        created_from=to_utc(args.created_from) if args.created_from else None,
        created_to=to_utc(args.created_to + timedelta(days=1)) if args.created_to else None,
        limit=MAX_ROWS + 1,
    )
    rows = [
        {"doc_no": d.doc_no, "status": d.status, "partner": d.partner, "source_document": d.ref_document.doc_no
         if d.ref_document else None, "expected_date": d.expected_date, "created_at": d.created_at,
         "posted_at": d.posted_at, "remark": d.remark}
        for d in docs
    ]
    return {"times_are": "UTC", **_rows(rows)}


class GetDocumentIn(_In):
    doc_no: str = Field(min_length=1, max_length=50, description="The document number, e.g. PO20261104-0052")


def get_document(ctx: ToolContext, args: GetDocumentIn) -> dict:
    doc = ctx.db.scalar(
        select(DocumentHeader).where(
            DocumentHeader.tenant_id == ctx.tenant_id, DocumentHeader.doc_no == args.doc_no.strip(),
            DocumentHeader.is_deleted == false(),
        )
    )
    if doc is None or doc.doc_type not in DOCUMENT_TYPES:
        raise ToolError(f"No document {args.doc_no!r}")
    ctx.require(DOCUMENT_TYPES[doc.doc_type][0])
    lines = [
        {"line": line.line_no, "sku": line.item.sku_code, "item": line.item.name, "uom": line.uom.code,
         "planned": line.qty_planned, "actual": line.qty_actual, "batch_no": line.batch_no,
         "from": line.from_location.code if line.from_location else None,
         "to": line.to_location.code if line.to_location else None}
        for line in sorted(doc.lines, key=lambda line: line.line_no)
    ]
    return {
        "doc_no": doc.doc_no, "type": DOCUMENT_TYPES[doc.doc_type][1], "status": doc.status, "partner": doc.partner,
        "location": doc.location, "source_document": doc.ref_document.doc_no if doc.ref_document else None,
        "expected_date": doc.expected_date, "created_at": doc.created_at, "posted_at": doc.posted_at,
        "remark": doc.remark, "times_are": "UTC", "lines": _rows(lines),
    }


class NoInput(_In):
    pass


def dashboard(ctx: ToolContext, _: NoInput) -> dict:
    data = ReportService(ctx.db, ctx.tenant_id).dashboard()
    return {k: v for k, v in data.items() if k != "trend"} | {"trend_last_14_days": data.get("trend")}


def order_shortages(ctx: ToolContext, _: NoInput) -> dict:
    rows = SalesOrderService(ctx.db, ctx.tenant_id, None).shortage_report()
    return _rows([_plain(r) for r in rows])


class ExpiringStockIn(_In):
    within_days: int = Field(default=30, ge=0, le=365, description="Expired, or expiring within this many days")


def expiring_stock(ctx: ToolContext, args: ExpiringStockIn) -> dict:
    return _rows(ReportService(ctx.db, ctx.tenant_id).expiry(args.within_days))


class TurnoverIn(_In):
    date_from: date = Field(description="First day, inclusive")
    date_to: date = Field(description="Last day, inclusive (at most 366 days after date_from)")
    keyword: str | None = Field(default=None, max_length=100, description="Only items whose SKU or name contains this")


def stock_turnover(ctx: ToolContext, args: TurnoverIn) -> dict:
    total, rows = ReportService(ctx.db, ctx.tenant_id).turnover(args.date_from, args.date_to, args.keyword, MAX_ROWS)
    return _rows(rows, total)


def zone_occupancy(ctx: ToolContext, _: NoInput) -> dict:
    return _rows(ReportService(ctx.db, ctx.tenant_id).occupancy())


_DOC_READ = tuple(permission for permission, _ in DOCUMENT_TYPES.values())

# Fixed order: the tool list is part of the cached prompt prefix
TOOLS: list[Tool] = [
    Tool("find_items", "Search items by SKU, name or barcode. Use it to find the SKU when the user names an item loosely.",
         FindItemsIn, ("item.read",), find_items),
    Tool("stock_on_hand", "Current stock of an item (per location and batch) and/or everything at one location, "
         "with on-hand, allocated and available quantities in base units.", StockOnHandIn, ("stock.read",), stock_on_hand),
    Tool("stock_movements", "Stock ledger of one item: every receipt, putaway, move, pick, shipment, adjustment and count "
         "difference over the last N days, with the document that caused it.", StockMovementsIn, ("stock.read",),
         stock_movements),
    Tool("list_documents", "List documents of one type, newest first, filtered by status, keyword and creation dates.",
         ListDocumentsIn, _DOC_READ, list_documents_tool),
    Tool("get_document", "One document by its number, with all its lines.", GetDocumentIn, _DOC_READ, get_document),
    Tool("dashboard", "Today's activity, work in progress (open orders, drafts to post, open picks and counts, shortage "
         "lines), stock health and the received/shipped trend of the last 14 days.", NoInput, ("report.read",), dashboard),
    Tool("order_shortages", "Sales order lines that could not be fully allocated, with what is available warehouse-wide.",
         NoInput, ("sales_order.read",), order_shortages),
    Tool("expiring_stock", "Batches that are expired or expire within N days, with location and quantity.",
         ExpiringStockIn, ("report.read",), expiring_stock),
    Tool("stock_turnover", "Per item for a date range: opening, received, shipped, other changes, closing, turnover and "
         "days on hand.", TurnoverIn, ("report.read",), stock_turnover),
    Tool("zone_occupancy", "Per zone: bins in use, locked bins, quantity on hand and capacity.", NoInput, ("report.read",),
         zone_occupancy),
]
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def tools_for(permissions: set[str]) -> list[Tool]:
    return [tool for tool in TOOLS if tool.offered_to(permissions)]
