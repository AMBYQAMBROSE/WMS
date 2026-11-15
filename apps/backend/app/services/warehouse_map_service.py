"""Warehouse map: every location of one warehouse with what it holds, and what happened where (live and replay).

The layout comes from the location tree itself (warehouse > zone > aisle > rack > bin), so a warehouse needs no
drawing or coordinates to get a map. Activity is read from the stock ledger (stock that moved) and from lines
confirmed on PDAs (picks, putaway puts, counts), which happen before anything is posted.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import false, func, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models.document import DocumentHeader, DocumentLine, DocumentLocation
from app.models.item import Item
from app.models.location import Location
from app.models.stock import StockBalance, StockLedger
from app.models.user import User
from app.services.batch_hold import active_recalls, held
from app.services.document_common import COUNT_IN_PROGRESS, DOC_COUNT, DOC_PICK, DOC_PUTAWAY, utcnow
from app.services.stock_service import MOVE_PICK_OUT

PICK_WINDOW_DAYS = 30
MAX_ACTIVITY_WINDOW = timedelta(days=2)
DEFAULT_ACTIVITY_WINDOW = timedelta(minutes=15)
MAX_EVENTS = 5000
RECENT_AT_BIN = 15
ZERO = 0


@dataclass
class WarehouseMapService:
    db: Session
    tenant_id: uuid.UUID

    # ------------------------------------------------------------ layout and state

    def _warehouses(self) -> list[Location]:
        return list(
            self.db.scalars(
                select(Location)
                .where(
                    Location.tenant_id == self.tenant_id, Location.location_type == "WAREHOUSE",
                    Location.is_active == true(), Location.is_deleted == false(),
                )
                .order_by(Location.code)
            )
        )

    def _warehouse(self, warehouse_id: uuid.UUID | None) -> Location | None:
        if warehouse_id is None:
            first = self._warehouses()
            return first[0] if first else None
        wh = self.db.get(Location, warehouse_id)
        if wh is None or wh.tenant_id != self.tenant_id or wh.is_deleted or wh.location_type != "WAREHOUSE":
            raise NotFoundError("Warehouse not found")
        return wh

    def _in_warehouse(self, wh: Location):
        return or_(Location.id == wh.id, Location.path.startswith(wh.path + "/", autoescape=True))

    def _counting_ids(self) -> set[uuid.UUID]:
        return set(
            self.db.scalars(
                select(DocumentLocation.location_id)
                .join(DocumentHeader, DocumentHeader.id == DocumentLocation.document_id)
                .where(
                    DocumentHeader.tenant_id == self.tenant_id, DocumentHeader.doc_type == DOC_COUNT,
                    DocumentHeader.status == COUNT_IN_PROGRESS,
                )
            )
        )

    def map(self, warehouse_id: uuid.UUID | None) -> dict:
        warehouses = self._warehouses()
        wh = self._warehouse(warehouse_id)
        result = {
            "warehouses": [{"id": w.id, "code": w.code, "name": w.name} for w in warehouses],
            "warehouse": {"id": wh.id, "code": wh.code, "name": wh.name} if wh else None,
            "nodes": [],
            "pick_window_days": PICK_WINDOW_DAYS,
            "generated_at": utcnow(),
        }
        if wh is None:
            return result

        locations = list(
            self.db.execute(
                select(
                    Location.id, Location.parent_id, Location.code, Location.name, Location.location_type,
                    Location.is_pickable, Location.is_locked, Location.capacity_qty,
                )
                .where(
                    Location.tenant_id == self.tenant_id, Location.is_active == true(), Location.is_deleted == false(),
                    self._in_warehouse(wh),
                )
                .order_by(Location.code)
            )
        )
        B = StockBalance
        in_wh = select(Location.id).where(Location.tenant_id == self.tenant_id, self._in_warehouse(wh))
        stock = {
            row.location_id: row
            for row in self.db.execute(
                select(
                    B.location_id,
                    func.sum(B.qty_on_hand).label("on_hand"),
                    func.sum(B.qty_allocated).label("allocated"),
                    func.count(func.distinct(B.item_id)).label("skus"),
                    func.min(B.expiry_date).label("expiry"),
                )
                .where(B.tenant_id == self.tenant_id, B.qty_on_hand > 0, B.location_id.in_(in_wh))
                .group_by(B.location_id)
            )
        }
        recalled = set(
            self.db.scalars(
                select(B.location_id)
                .where(B.tenant_id == self.tenant_id, B.qty_on_hand > 0, B.location_id.in_(in_wh),
                       held(self.tenant_id, B.item_id, B.batch_no))
                .distinct()
            )
        )
        L = StockLedger
        picks = dict(
            self.db.execute(
                select(L.location_id, func.count())
                .where(
                    L.tenant_id == self.tenant_id, L.movement_type == MOVE_PICK_OUT,
                    L.occurred_at >= utcnow() - timedelta(days=PICK_WINDOW_DAYS), L.location_id.in_(in_wh),
                )
                .group_by(L.location_id)
            ).all()
        )
        counting = self._counting_ids()

        for loc in locations:
            s = stock.get(loc.id)
            result["nodes"].append({
                "id": loc.id,
                # The warehouse is the root of the map, whatever sits above it
                "parent_id": None if loc.id == wh.id else loc.parent_id,
                "code": loc.code,
                "name": loc.name,
                "location_type": loc.location_type,
                "is_pickable": loc.is_pickable,
                "is_locked": loc.is_locked,
                "is_counting": loc.id in counting,
                "capacity_qty": loc.capacity_qty,
                "qty_on_hand": s.on_hand if s else ZERO,
                "qty_allocated": s.allocated if s else ZERO,
                "sku_count": s.skus if s else 0,
                "nearest_expiry": s.expiry if s else None,
                "has_recalled": loc.id in recalled,
                "picks": picks.get(loc.id, 0),
            })
        return result

    # ------------------------------------------------------------ activity

    def activity(
        self,
        warehouse_id: uuid.UUID | None,
        since: datetime | None,
        until: datetime | None,
        location_id: uuid.UUID | None = None,
        limit: int = MAX_EVENTS,
    ) -> dict:
        until = until or utcnow()
        since = since or until - DEFAULT_ACTIVITY_WINDOW
        if since >= until:
            raise DomainError("The start of the period must be before its end")
        if until - since > MAX_ACTIVITY_WINDOW:
            raise DomainError("Activity can be shown for at most 2 days at a time")
        wh = self._warehouse(warehouse_id)
        if wh is None:
            return {"since": since, "until": until, "truncated": False, "events": []}

        in_wh = select(Location.id).where(Location.tenant_id == self.tenant_id, self._in_warehouse(wh))
        if location_id is not None:
            in_wh = in_wh.where(Location.id == location_id)
        L, line, doc = StockLedger, DocumentLine, DocumentHeader
        user_name = func.coalesce(User.display_name, User.username)
        movements = self.db.execute(
            select(
                L.occurred_at, L.location_id, L.movement_type, L.qty_change, Item.sku_code,
                doc.id.label("doc_id"), doc.doc_type, doc.doc_no, L.created_by, user_name.label("user_name"),
            )
            .join(Item, Item.id == L.item_id)
            .outerjoin(line, line.id == L.ref_document_line_id)
            .outerjoin(doc, doc.id == line.document_id)
            .outerjoin(User, User.id == L.created_by)
            .where(L.tenant_id == self.tenant_id, L.occurred_at >= since, L.occurred_at < until, L.location_id.in_(in_wh))
            .order_by(L.occurred_at.desc())
            .limit(limit + 1)
        ).all()

        # PDA work shows up as it is done, before the document is posted: picks at the bin they come from,
        # putaway puts and counts at the bin they go to
        scans = self.db.execute(
            select(
                line.confirmed_at, line.from_location_id, line.to_location_id, doc.doc_type, line.qty_actual,
                Item.sku_code, doc.id.label("doc_id"), doc.doc_no, line.confirmed_by, user_name.label("user_name"),
            )
            .join(doc, doc.id == line.document_id)
            .join(Item, Item.id == line.item_id)
            .outerjoin(User, User.id == line.confirmed_by)
            .where(
                line.tenant_id == self.tenant_id, line.confirmed_at.is_not(None),
                line.confirmed_at >= since, line.confirmed_at < until,
                doc.doc_type.in_([DOC_PICK, DOC_PUTAWAY, DOC_COUNT]),
                or_(line.from_location_id.in_(in_wh), line.to_location_id.in_(in_wh)),
            )
            .order_by(line.confirmed_at.desc())
            .limit(limit + 1)
        ).all()

        events = [
            {
                "at": r.occurred_at, "location_id": r.location_id, "kind": "MOVEMENT", "movement_type": r.movement_type,
                "doc_type": r.doc_type, "doc_no": r.doc_no, "document_id": r.doc_id, "sku_code": r.sku_code,
                "qty": r.qty_change, "user_id": r.created_by, "user_name": r.user_name,
            }
            for r in movements
        ]
        for r in scans:
            location = r.from_location_id if r.doc_type == DOC_PICK else (r.to_location_id or r.from_location_id)
            if location is None or (location_id is not None and location != location_id):
                continue
            events.append({
                "at": r.confirmed_at, "location_id": location, "kind": "SCAN", "movement_type": None,
                "doc_type": r.doc_type, "doc_no": r.doc_no, "document_id": r.doc_id, "sku_code": r.sku_code,
                "qty": r.qty_actual, "user_id": r.confirmed_by, "user_name": r.user_name,
            })
        events.sort(key=lambda e: e["at"], reverse=True)
        truncated = len(events) > limit
        # Keep the newest when there is too much, then hand them out oldest first (the order to replay them in)
        events = events[:limit]
        events.reverse()
        return {"since": since, "until": until, "truncated": truncated, "events": events}

    # ------------------------------------------------------------ one bin

    def bin_detail(self, location_id: uuid.UUID) -> dict:
        location = self.db.get(Location, location_id)
        if location is None or location.tenant_id != self.tenant_id or location.is_deleted:
            raise NotFoundError("Location not found")
        balances = list(
            self.db.scalars(
                select(StockBalance)
                .where(StockBalance.tenant_id == self.tenant_id, StockBalance.location_id == location_id,
                       StockBalance.qty_on_hand > 0)
                .order_by(StockBalance.expiry_date, StockBalance.created_at)
            ).unique()
        )
        recalls = active_recalls(self.db, self.tenant_id)
        counting_doc = self.db.scalars(
            select(DocumentHeader)
            .join(DocumentLocation, DocumentLocation.document_id == DocumentHeader.id)
            .where(
                DocumentHeader.tenant_id == self.tenant_id, DocumentHeader.doc_type == DOC_COUNT,
                DocumentHeader.status == COUNT_IN_PROGRESS, DocumentLocation.location_id == location_id,
            )
        ).unique().first()
        until = utcnow()
        warehouse = self._warehouse_of(location)
        recent = self.activity(warehouse.id, until - MAX_ACTIVITY_WINDOW, until, location_id, RECENT_AT_BIN)["events"] \
            if warehouse else []
        recent.reverse()
        return {
            "location": location,
            "path": location.path,
            "is_locked": location.is_locked,
            "is_counting": counting_doc is not None,
            "counting_doc": counting_doc,
            "capacity_qty": location.capacity_qty,
            "stock": [
                {
                    "item": b.item, "batch_no": b.batch_no, "expiry_date": b.expiry_date,
                    "qty_on_hand": b.qty_on_hand, "qty_allocated": b.qty_allocated,
                    "recall": recalls.get((b.item_id, b.batch_no)),
                }
                for b in balances
            ],
            "recent": recent,
        }

    def _warehouse_of(self, location: Location) -> Location | None:
        return next(
            (w for w in self._warehouses() if location.path == w.path or location.path.startswith(w.path + "/")), None
        )
