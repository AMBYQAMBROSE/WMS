"""Dashboard and reports. Everything is computed from the stock ledger / balances / documents; no summary tables (consider materializing at larger volumes, see PLAN 4.4).

Time: the database stores UTC; a report "day" is split by settings.business_timezone.
Quantities: always base units.
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from time import monotonic
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, distinct, false, func, literal_column, or_, select, true
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import DomainError
from app.models.audit import AuditLog
from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader, DocumentLine
from app.models.item import Item, Uom
from app.models.location import Location
from app.models.stock import StockBalance, StockLedger
from app.models.user import User
from app.services import stock_service as st
from app.services.document_common import (
    COUNT_IN_PROGRESS,
    DOC_COUNT,
    DOC_GRN,
    DOC_PICK,
    DOC_PO,
    DOC_PUTAWAY,
    DOC_SHIP,
    DOC_SO,
)
from app.services.sales_order_service import SalesOrderService

# Ledger categories: in/out reports only count stock entering or leaving the warehouse; internal transfers (putaway, move, pick) are excluded
RECEIVED_TYPES = (st.MOVE_RECEIVE, st.MOVE_RETURN_IN)
SHIPPED_TYPES = (st.MOVE_SHIP_OUT, st.MOVE_RETURN_OUT)
OTHER_TYPES = (st.MOVE_ADJUST_IN, st.MOVE_ADJUST_OUT, st.MOVE_COUNT_GAIN, st.MOVE_COUNT_LOSS,
               st.MOVE_REPACK_IN, st.MOVE_REPACK_OUT)
MAX_REPORT_DAYS = 366
DASHBOARD_TTL_SECONDS = 30
_DASHBOARD_CACHE: dict = {}

ZERO = Decimal(0)


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.business_timezone)


def today_local() -> date:
    return datetime.now(_tz()).date()


def to_utc(day: date) -> datetime:
    """UTC time of local midnight on the given day (database times are naive UTC)"""
    local = datetime.combine(day, time.min, tzinfo=_tz())
    return local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def _offset_minutes() -> int:
    return int(datetime.now(_tz()).utcoffset().total_seconds() // 60)


def check_range(date_from: date, date_to: date) -> tuple[datetime, datetime, int]:
    if date_to < date_from:
        raise DomainError("The end date cannot be before the start date")
    days = (date_to - date_from).days + 1
    if days > MAX_REPORT_DAYS:
        raise DomainError(f"The date range cannot exceed {MAX_REPORT_DAYS} days")
    return to_utc(date_from), to_utc(date_to + timedelta(days=1)), days


# SQL Server allows at most 2100 parameters per statement: split IN lists when loading by ID
IN_CHUNK = 1000


def load_by_ids(db: Session, model, ids) -> dict:
    ids = list(ids)
    found = {}
    for i in range(0, len(ids), IN_CHUNK):
        found.update({row.id: row for row in db.scalars(select(model).where(model.id.in_(ids[i:i + IN_CHUNK])))})
    return found


# Reports read item and base unit columns directly instead of loading ORM objects (matters with tens of thousands of rows)
_ITEM_COLUMNS = (
    Item.sku_code.label("item_sku"),
    Item.name.label("item_name"),
    Item.is_batch_managed.label("item_batch"),
    Item.is_expiry_managed.label("item_expiry"),
    Uom.id.label("uom_id"),
    Uom.code.label("uom_code"),
    Uom.name.label("uom_name"),
)


def _item_brief(r) -> dict:
    return {
        "id": r["item_id"],
        "sku_code": r["item_sku"],
        "name": r["item_name"],
        "is_batch_managed": r["item_batch"],
        "is_expiry_managed": r["item_expiry"],
        "base_uom": {"id": r["uom_id"], "code": r["uom_code"], "name": r["uom_name"]},
    }


def _num(value) -> Decimal:
    return Decimal(value) if value is not None else ZERO


@dataclass
class ReportService:
    db: Session
    tenant_id: uuid.UUID

    # ------------------------------------------------------------ dashboard

    def dashboard(self) -> dict:
        """Dashboard data is cached per tenant for 30 s (per process), so dozens of open dashboards cost one computation.
        The cache is also keyed on the tenant's latest change (an index seek on the audit log): live updates refetch
        the dashboard right after a change, and must get the new numbers, not a cached copy from before it."""
        marker = self.db.scalar(select(func.max(AuditLog.occurred_at)).where(AuditLog.tenant_id == self.tenant_id))
        cached = _DASHBOARD_CACHE.get(self.tenant_id)
        if cached and cached[0] > monotonic() and cached[1] == marker:
            return cached[2]
        data = self._dashboard()
        _DASHBOARD_CACHE[self.tenant_id] = (monotonic() + DASHBOARD_TTL_SECONDS, marker, data)
        return data

    def occupancy(self) -> list[dict]:
        """Bin occupancy per zone, for the dashboard heatmap. Bins are grouped under their nearest ZONE ancestor,
        or under their warehouse when there is no zone in between (found from the materialized location path)."""
        active = and_(Location.tenant_id == self.tenant_id, Location.is_active == true(), Location.is_deleted == false())
        areas = {
            row.path: row
            for row in self.db.execute(
                select(Location.id, Location.code, Location.name, Location.location_type, Location.path)
                .where(active, Location.location_type.in_(["WAREHOUSE", "ZONE"]))
            )
        }
        B = StockBalance
        stock = dict(
            self.db.execute(
                select(B.location_id, func.sum(B.qty_on_hand))
                .where(B.tenant_id == self.tenant_id, B.qty_on_hand > 0)
                .group_by(B.location_id)
            ).all()
        )

        result: dict[str, dict] = {}
        for bin_ in self.db.execute(
            select(Location.id, Location.path, Location.is_locked, Location.capacity_qty)
            .where(active, Location.location_type == "BIN")
        ):
            segments = bin_.path.split("/")[1:]  # "/WH/Z1/A1/R1/B1" -> ["WH", "Z1", "A1", "R1", "B1"]
            prefixes = ["/" + "/".join(segments[:i]) for i in range(len(segments) - 1, 0, -1)]
            area_path = next((p for p in prefixes if p in areas and areas[p].location_type == "ZONE"), None) \
                or next((p for p in prefixes if p in areas), None)
            if area_path is None:
                continue
            area = areas[area_path]
            row = result.setdefault(area_path, {
                "id": area.id, "code": area.code, "name": area.name, "location_type": area.location_type,
                "warehouse_code": segments[0], "bins_total": 0, "bins_used": 0, "bins_locked": 0,
                "qty_on_hand": ZERO, "capacity_qty": None,
            })
            qty = stock.get(bin_.id) or ZERO
            row["bins_total"] += 1
            row["bins_used"] += qty > 0
            row["bins_locked"] += bool(bin_.is_locked)
            row["qty_on_hand"] += qty
            if bin_.capacity_qty is not None:
                row["capacity_qty"] = (row["capacity_qty"] or ZERO) + bin_.capacity_qty
        return sorted(result.values(), key=lambda r: (r["warehouse_code"], r["location_type"] != "WAREHOUSE", r["code"]))

    def _dashboard(self) -> dict:
        today = today_local()
        start, end = to_utc(today), to_utc(today + timedelta(days=1))
        L = StockLedger

        def ledger_sum(types, since, until):
            return self.db.scalar(
                select(func.sum(L.qty_change)).where(
                    L.tenant_id == self.tenant_id, L.movement_type.in_(types),
                    L.occurred_at >= since, L.occurred_at < until,
                )
            )

        def posted_count(doc_type):
            return self.db.scalar(
                select(func.count()).where(
                    DocumentHeader.tenant_id == self.tenant_id, DocumentHeader.doc_type == doc_type,
                    DocumentHeader.posted_at >= start, DocumentHeader.posted_at < end,
                )
            )

        status_counts = dict(
            ((t, s), n)
            for t, s, n in self.db.execute(
                select(DocumentHeader.doc_type, DocumentHeader.status, func.count())
                .where(DocumentHeader.tenant_id == self.tenant_id, DocumentHeader.is_deleted == false())
                .group_by(DocumentHeader.doc_type, DocumentHeader.status)
            )
        )

        def backlog(doc_type, *statuses):
            return sum(status_counts.get((doc_type, s), 0) for s in statuses)

        B = StockBalance
        in_stock = and_(B.tenant_id == self.tenant_id, B.qty_on_hand > 0)
        sku_count, qty_on_hand, qty_allocated = self.db.execute(
            select(func.count(distinct(B.item_id)), func.sum(B.qty_on_hand), func.sum(B.qty_allocated)).where(in_stock)
        ).one()
        bins_total = self.db.scalar(
            select(func.count()).where(
                Location.tenant_id == self.tenant_id, Location.location_type == "BIN",
                Location.is_active == true(), Location.is_deleted == false(),
            )
        )
        bins_used = self.db.scalar(
            select(func.count(distinct(B.location_id)))
            .join(Location, Location.id == B.location_id)
            .where(in_stock, Location.location_type == "BIN")
        )
        expired = self.db.scalar(select(func.sum(B.qty_on_hand)).where(in_stock, B.expiry_date < today))
        expiring = self.db.scalar(
            select(func.sum(B.qty_on_hand)).where(
                in_stock, B.expiry_date >= today, B.expiry_date <= today + timedelta(days=30)
            )
        )

        return {
            "date": today,
            "today": {
                "received_qty": _num(ledger_sum([st.MOVE_RECEIVE], start, end)),
                "shipped_qty": -_num(ledger_sum([st.MOVE_SHIP_OUT], start, end)),
                "grn_posted": posted_count(DOC_GRN),
                "shipments_posted": posted_count(DOC_SHIP),
            },
            "backlog": {
                "po_open": backlog(DOC_PO, "CONFIRMED", "PARTIALLY_RECEIVED"),
                "grn_draft": backlog(DOC_GRN, "DRAFT"),
                "putaway_draft": backlog(DOC_PUTAWAY, "DRAFT"),
                "so_open": backlog(DOC_SO, "CONFIRMED", "IN_PROGRESS", "PARTIALLY_SHIPPED"),
                "pick_open": backlog(DOC_PICK, "OPEN"),
                "shipment_draft": backlog(DOC_SHIP, "DRAFT"),
                "count_open": backlog(DOC_COUNT, COUNT_IN_PROGRESS),
                "shortage_lines": len(SalesOrderService(self.db, self.tenant_id, None).shortage_report()),
            },
            "stock": {
                "sku_count": sku_count or 0,
                "qty_on_hand": _num(qty_on_hand),
                "qty_allocated": _num(qty_allocated),
                "bins_total": bins_total or 0,
                "bins_used": bins_used or 0,
                "expired_qty": _num(expired),
                "expiring_30d_qty": _num(expiring),
            },
            "trend": self.daily_flow(today - timedelta(days=13), today),
        }

    def daily_flow(self, date_from: date, date_to: date) -> list[dict]:
        """Received and shipped quantity per day (days split by the business time zone)"""
        start, end, _ = check_range(date_from, date_to)
        L = StockLedger
        # DATEADD's unit must be a keyword; the offset is a literal rather than a parameter so SQL Server treats SELECT and GROUP BY as the same expression
        day = literal_column(f"CAST(DATEADD(minute, {_offset_minutes():d}, stock_ledger.occurred_at) AS date)")
        rows = self.db.execute(
            select(
                day.label("day"),
                func.sum(case((L.movement_type == st.MOVE_RECEIVE, L.qty_change), else_=0)),
                func.sum(case((L.movement_type == st.MOVE_SHIP_OUT, -L.qty_change), else_=0)),
            )
            .where(
                L.tenant_id == self.tenant_id,
                L.movement_type.in_([st.MOVE_RECEIVE, st.MOVE_SHIP_OUT]),
                L.occurred_at >= start, L.occurred_at < end,
            )
            .group_by(day)
        ).all()
        by_day = {r[0]: (r[1], r[2]) for r in rows}
        result = []
        d = date_from
        while d <= date_to:
            received, shipped = by_day.get(d, (ZERO, ZERO))
            result.append({"date": d, "received_qty": _num(received), "shipped_qty": _num(shipped)})
            d += timedelta(days=1)
        return result

    # ------------------------------------------------------------ stock turnover

    def turnover(self, date_from: date, date_to: date, keyword: str | None, limit: int | None) -> tuple[int, list[dict]]:
        """Return (total rows, first `limit` rows); limit=None returns everything (for export). Aggregation, item join, sorting and truncation all happen in the database"""
        start, end, days = check_range(date_from, date_to)
        L, B = StockLedger, StockBalance
        in_period = and_(L.occurred_at >= start, L.occurred_at < end)

        def period_sum(types, sign=1):
            return func.sum(case((and_(in_period, L.movement_type.in_(types)), sign * L.qty_change), else_=0))

        # Opening/closing are derived as "current balance minus later ledger entries", so only ledger entries since the start date are scanned (time index);
        # summing everything before the start date gets slower as history grows. Relies on ledger total == balance (guaranteed by posting in one transaction)
        now = (
            select(B.item_id, func.sum(B.qty_on_hand).label("on_hand"))
            .where(B.tenant_id == self.tenant_id)
            .group_by(B.item_id)
            .subquery()
        )
        moves = (
            select(
                L.item_id,
                period_sum(RECEIVED_TYPES).label("received"),
                period_sum(SHIPPED_TYPES, -1).label("shipped"),
                period_sum(OTHER_TYPES).label("other"),
                func.sum(L.qty_change).label("since_start"),
                func.sum(case((L.occurred_at >= end, L.qty_change), else_=0)).label("since_end"),
            )
            .where(L.tenant_id == self.tenant_id, L.occurred_at >= start)
            .group_by(L.item_id)
            .subquery()
        )
        on_hand = func.coalesce(now.c.on_hand, 0)
        agg = (
            select(
                func.coalesce(now.c.item_id, moves.c.item_id).label("item_id"),
                (on_hand - func.coalesce(moves.c.since_start, 0)).label("opening"),
                func.coalesce(moves.c.received, 0).label("received"),
                func.coalesce(moves.c.shipped, 0).label("shipped"),
                func.coalesce(moves.c.other, 0).label("other"),
                (on_hand - func.coalesce(moves.c.since_end, 0)).label("closing"),
            )
            .select_from(now.outerjoin(moves, moves.c.item_id == now.c.item_id, full=True))
            .subquery()
        )
        average = (agg.c.opening + agg.c.closing) / 2
        # Turnover = shipped in period / average stock; meaningless when average stock <= 0
        turns = case((average > 0, agg.c.shipped / average), else_=None)
        stmt = (
            select(agg, average.label("average"), turns.label("turns"), func.count().over().label("total"), *_ITEM_COLUMNS)
            .join(Item, Item.id == agg.c.item_id)
            .join(Uom, Uom.id == Item.base_uom_id)
            .where(or_(agg.c.opening != 0, agg.c.received != 0, agg.c.shipped != 0, agg.c.other != 0, agg.c.closing != 0))
            .order_by(case((turns.is_(None), 1), else_=0), turns.desc(), Item.sku_code)
        )
        if kw := (keyword or "").strip():
            stmt = stmt.where(or_(Item.sku_code.contains(kw, autoescape=True), Item.name.contains(kw, autoescape=True)))
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = self.db.execute(stmt).mappings().all()
        result = []
        for r in rows:
            turn = Decimal(r["turns"]) if r["turns"] is not None else None
            result.append({
                "item": _item_brief(r),
                **{k: _num(r[k]) for k in ("opening", "received", "shipped", "other", "closing", "average")},
                "turnover": round(turn, 2) if turn is not None else None,
                "days_on_hand": round(Decimal(days) / turn, 1) if turn else None,
            })
        return (rows[0]["total"] if rows else 0), result

    # ------------------------------------------------------------ picker performance

    def picker_kpi(self, date_from: date, date_to: date) -> list[dict]:
        start, end, _ = check_range(date_from, date_to)
        line, doc = DocumentLine, DocumentHeader
        rows = self.db.execute(
            select(
                line.confirmed_by,
                func.count(distinct(line.document_id)),
                func.count(),
                func.sum(line.qty_actual),
                func.sum(case((line.qty_actual < line.qty_planned, 1), else_=0)),
                func.min(line.confirmed_at),
                func.max(line.confirmed_at),
            )
            .join(doc, doc.id == line.document_id)
            .where(
                doc.tenant_id == self.tenant_id, doc.doc_type == DOC_PICK, doc.status != "CANCELLED",
                line.confirmed_by.is_not(None), line.confirmed_at >= start, line.confirmed_at < end,
            )
            .group_by(line.confirmed_by)
        ).all()
        users = load_by_ids(self.db, User, {r[0] for r in rows})
        result = [
            {
                "user_id": user_id,
                "username": users[user_id].username if user_id in users else "?",
                "display_name": users[user_id].display_name if user_id in users else "?",
                "picks": picks,
                "lines": lines,
                "qty": _num(qty),
                "short_lines": short or 0,
                # Fill rate: share of lines where picked = requested
                "fill_rate": round(Decimal(lines - (short or 0)) / lines * 100, 1) if lines else None,
                "first_at": first_at,
                "last_at": last_at,
            }
            for user_id, picks, lines, qty, short, first_at, last_at in rows
        ]
        result.sort(key=lambda r: -r["lines"])
        return result

    # ------------------------------------------------------------ expiring stock

    def expiry(self, within_days: int) -> list[dict]:
        today = today_local()
        B = StockBalance
        rows = list(
            self.db.scalars(
                select(B)
                .where(
                    B.tenant_id == self.tenant_id, B.qty_on_hand > 0, B.expiry_date.is_not(None),
                    B.expiry_date <= today + timedelta(days=within_days),
                )
                .order_by(B.expiry_date)
            )
        )
        return [
            {
                "item": b.item,
                "location_code": b.location.code,
                "batch_no": b.batch_no,
                "expiry_date": b.expiry_date,
                "days_left": (b.expiry_date - today).days,
                "qty_on_hand": b.qty_on_hand,
                "qty_allocated": b.qty_allocated,
            }
            for b in rows
        ]

    # ------------------------------------------------------------ partner ledger

    def partner_ledger(self, date_from: date, date_to: date, partner_id: uuid.UUID | None,
                       limit: int | None) -> tuple[int, list[dict]]:
        """Received / returned to supplier / shipped / customer-returned quantity per partner and item in the period (Ninso Supplier/OutletLedger)"""
        start, end, _ = check_range(date_from, date_to)
        L, line, doc = StockLedger, DocumentLine, DocumentHeader
        types = (st.MOVE_RECEIVE, st.MOVE_RETURN_OUT, st.MOVE_SHIP_OUT, st.MOVE_RETURN_IN)

        def by_type(movement, sign=1):
            return func.sum(case((L.movement_type == movement, sign * L.qty_change), else_=0))

        agg = (
            select(
                doc.partner_id,
                L.item_id,
                by_type(st.MOVE_RECEIVE).label("received"),
                by_type(st.MOVE_RETURN_OUT, -1).label("returned_to_supplier"),
                by_type(st.MOVE_SHIP_OUT, -1).label("shipped"),
                by_type(st.MOVE_RETURN_IN).label("returned_by_customer"),
                func.count(distinct(doc.id)).label("documents"),
            )
            .join(line, line.id == L.ref_document_line_id)
            .join(doc, doc.id == line.document_id)
            .where(
                L.tenant_id == self.tenant_id, L.movement_type.in_(types),
                L.occurred_at >= start, L.occurred_at < end, doc.partner_id.is_not(None),
            )
            .group_by(doc.partner_id, L.item_id)
        )
        if partner_id:
            agg = agg.where(doc.partner_id == partner_id)
        agg = agg.subquery()
        P = BusinessPartner
        stmt = (
            select(agg, func.count().over().label("total"), P.code.label("partner_code"), P.name.label("partner_name"), *_ITEM_COLUMNS)
            .join(P, P.id == agg.c.partner_id)
            .join(Item, Item.id == agg.c.item_id)
            .join(Uom, Uom.id == Item.base_uom_id)
            .order_by(P.code, Item.sku_code)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = self.db.execute(stmt).mappings().all()
        result = [
            {
                "partner": {"id": r["partner_id"], "code": r["partner_code"], "name": r["partner_name"]},
                "item": _item_brief(r),
                **{k: _num(r[k]) for k in ("received", "returned_to_supplier", "shipped", "returned_by_customer")},
                "documents": r["documents"],
            }
            for r in rows
        ]
        return (rows[0]["total"] if rows else 0), result

