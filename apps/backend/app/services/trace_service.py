"""Batch traceability: where a batch came from, where it is now and where it went, read from the stock ledger.

Every stock change of a batch has a ledger row pointing at the document line that caused it, so the ledger alone gives
the whole chain: supplier -> receipt (and its purchase order) -> moves inside the warehouse -> shipments (and their
sales orders, vehicles) -> customers. Stock of one batch is interchangeable, so the trace says which documents brought
the batch in and which took it out, not which piece went where.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader, DocumentLine, ShipmentInfo
from app.models.item import Item
from app.models.location import Location
from app.models.stock import StockBalance, StockLedger
from app.models.user import User
from app.services.attachment_service import DOCUMENT_PERMISSIONS
from app.services.batch_hold import RECALL_ACTIVE, active_recall
from app.services.document_common import DOC_RECALL, DOC_SHIP
from app.services.stock_service import (
    MOVE_ADJUST_IN,
    MOVE_ADJUST_OUT,
    MOVE_COUNT_GAIN,
    MOVE_COUNT_LOSS,
    MOVE_RECEIVE,
    MOVE_REPACK_IN,
    MOVE_REPACK_OUT,
    MOVE_RETURN_IN,
    MOVE_RETURN_OUT,
    MOVE_SHIP_OUT,
)

INBOUND = (MOVE_RECEIVE, MOVE_RETURN_IN, MOVE_REPACK_IN, MOVE_ADJUST_IN, MOVE_COUNT_GAIN)
OUTBOUND = (MOVE_SHIP_OUT, MOVE_RETURN_OUT, MOVE_REPACK_OUT, MOVE_ADJUST_OUT, MOVE_COUNT_LOSS)
MAX_LEDGER_ROWS = 50_000
TIMELINE_ROWS = 500
SEARCH_LIMIT = 50
ZERO = Decimal(0)


def _brief(doc: DocumentHeader | None) -> dict | None:
    return {"id": doc.id, "doc_type": doc.doc_type, "doc_no": doc.doc_no, "status": doc.status} if doc else None


def _partner(p: BusinessPartner | None) -> dict | None:
    if p is None:
        return None
    return {
        "id": p.id, "code": p.code, "name": p.name,
        "contact_name": p.contact_name, "contact_phone": p.contact_phone, "address": p.address,
    }


@dataclass
class TraceService:
    db: Session
    tenant_id: uuid.UUID

    def _item(self, item_id: uuid.UUID) -> Item:
        item = self.db.get(Item, item_id)
        if item is None or item.tenant_id != self.tenant_id or item.is_deleted:
            raise NotFoundError("Item not found")
        return item

    # ------------------------------------------------------------ finding a batch

    def search(self, q: str | None, item_id: uuid.UUID | None) -> list[dict]:
        """Batches whose number starts with q (and/or of one item), most recently active first"""
        needle = (q or "").strip()
        if not needle and item_id is None:
            raise DomainError("Enter a batch number or choose an item")
        L = StockLedger
        stmt = (
            select(L.item_id, L.batch_no, func.min(L.occurred_at), func.max(L.occurred_at))
            .where(L.tenant_id == self.tenant_id, L.batch_no.is_not(None))
            .group_by(L.item_id, L.batch_no)
            .order_by(func.max(L.occurred_at).desc())
            .limit(SEARCH_LIMIT)
        )
        if needle:
            stmt = stmt.where(L.batch_no.startswith(needle, autoescape=True))
        if item_id is not None:
            stmt = stmt.where(L.item_id == item_id)
        rows = self.db.execute(stmt).all()
        if not rows:
            return []
        items = {i.id: i for i in self.db.scalars(select(Item).where(Item.id.in_({r[0] for r in rows})))}
        B = StockBalance
        on_hand = {
            (r.item_id, r.batch_no): r.qty
            for r in self.db.execute(
                select(B.item_id, B.batch_no, func.sum(B.qty_on_hand).label("qty"))
                .where(B.tenant_id == self.tenant_id, B.item_id.in_(items.keys()),
                       B.batch_no.in_({r[1] for r in rows}))
                .group_by(B.item_id, B.batch_no)
            )
        }
        return [
            {
                "item": items[item_id_], "batch_no": batch, "first_seen": first, "last_seen": last,
                "qty_on_hand": on_hand.get((item_id_, batch), ZERO),
                "recalled": active_recall(self.db, self.tenant_id, item_id_, batch) is not None,
            }
            for item_id_, batch, first, last in rows
            if item_id_ in items
        ]

    # ------------------------------------------------------------ one batch, end to end

    def trace(self, item_id: uuid.UUID, batch_no: str) -> dict:
        item = self._item(item_id)
        batch_no = batch_no.strip()
        L, line, doc = StockLedger, DocumentLine, DocumentHeader
        rows = self.db.execute(
            select(
                L.occurred_at, L.movement_type, L.qty_change, L.expiry_date, L.location_id,
                doc.id.label("doc_id"), func.coalesce(User.display_name, User.username).label("user_name"),
            )
            .outerjoin(line, line.id == L.ref_document_line_id)
            .outerjoin(doc, doc.id == line.document_id)
            .outerjoin(User, User.id == L.created_by)
            .where(L.tenant_id == self.tenant_id, L.item_id == item.id, L.batch_no == batch_no)
            .order_by(L.occurred_at, L.id)
            .limit(MAX_LEDGER_ROWS)
        ).all()

        B = StockBalance
        balances = list(
            self.db.scalars(
                select(B).where(B.tenant_id == self.tenant_id, B.item_id == item.id, B.batch_no == batch_no,
                                B.qty_on_hand > 0)
            ).unique()
        )
        pending_lines = list(
            self.db.execute(
                select(doc.id, line.qty_actual, line.expiry_date)
                .join(line, line.document_id == doc.id)
                .where(doc.tenant_id == self.tenant_id, doc.doc_type == DOC_SHIP, doc.status == "DRAFT",
                       doc.is_deleted == false(), line.item_id == item.id, line.batch_no == batch_no)
            ).all()
        )
        if not rows and not balances:
            raise NotFoundError(f"Batch {batch_no} of item {item.sku_code} has never been in stock")

        doc_ids = {r.doc_id for r in rows if r.doc_id} | {d for d, _, _ in pending_lines}
        docs = self._documents(doc_ids)
        locations = self._locations({r.location_id for r in rows} | {b.location_id for b in balances})

        # One flow per document and direction: a shipment taking the batch from two staging docks is one shipment
        flows: dict[tuple[uuid.UUID | None, str], dict] = {}
        totals: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for r in rows:
            if r.movement_type not in INBOUND and r.movement_type not in OUTBOUND:
                continue
            qty = abs(r.qty_change)
            totals[r.movement_type] += qty
            d = docs.get(r.doc_id)
            key = (r.doc_id, r.movement_type)
            flow = flows.get(key)
            if flow is None:
                flow = flows[key] = self._flow(d, r.movement_type, r.occurred_at)
            flow["qty"] += qty

        pending: dict[uuid.UUID, dict] = {}
        for doc_id, qty, _ in pending_lines:
            d = docs[doc_id]
            flow = pending.setdefault(doc_id, self._flow(d, MOVE_SHIP_OUT, d.created_at))
            flow["qty"] += qty

        inbound = sorted((f for (_, t), f in flows.items() if t in INBOUND), key=lambda f: f["at"])
        outbound = sorted((f for (_, t), f in flows.items() if t in OUTBOUND), key=lambda f: f["at"])
        shipments = [f for f in outbound if f["movement_type"] == MOVE_SHIP_OUT]
        recalls = list(
            self.db.scalars(
                select(doc)
                .join(line, line.document_id == doc.id)
                .where(doc.tenant_id == self.tenant_id, doc.doc_type == DOC_RECALL, doc.is_deleted == false(),
                       line.item_id == item.id, line.batch_no == batch_no)
                .order_by(doc.created_at.desc())
            ).unique()
        )
        timeline = rows[-TIMELINE_ROWS:]
        timeline.reverse()
        return {
            "item": item,
            "batch_no": batch_no,
            "expiry_dates": sorted({r.expiry_date for r in rows if r.expiry_date} | {b.expiry_date for b in balances if b.expiry_date}),
            "summary": {
                "received": totals[MOVE_RECEIVE],
                "returned_in": totals[MOVE_RETURN_IN],
                "other_in": totals[MOVE_REPACK_IN] + totals[MOVE_ADJUST_IN] + totals[MOVE_COUNT_GAIN],
                "shipped": totals[MOVE_SHIP_OUT],
                "returned_out": totals[MOVE_RETURN_OUT],
                "other_out": totals[MOVE_REPACK_OUT] + totals[MOVE_ADJUST_OUT] + totals[MOVE_COUNT_LOSS],
                "qty_on_hand": sum((b.qty_on_hand for b in balances), ZERO),
                "qty_allocated": sum((b.qty_allocated for b in balances), ZERO),
                "customers": len({f["partner"]["id"] for f in shipments if f["partner"]}),
                "shipments": len(shipments),
                "suppliers": len({f["partner"]["id"] for f in inbound if f["movement_type"] == MOVE_RECEIVE and f["partner"]}),
            },
            "inbound": inbound,
            "outbound": outbound,
            "stock": sorted(
                (
                    {"location": b.location, "expiry_date": b.expiry_date, "qty_on_hand": b.qty_on_hand,
                     "qty_allocated": b.qty_allocated}
                    for b in balances
                ),
                key=lambda s: s["location"].code,
            ),
            "pending_shipments": list(pending.values()),
            "movements": [
                {
                    "at": r.occurred_at, "movement_type": r.movement_type, "qty": r.qty_change,
                    "location": locations[r.location_id], "document": _brief(docs.get(r.doc_id)),
                    "user_name": r.user_name,
                }
                for r in timeline
            ],
            "movements_total": len(rows),
            "recalls": [_brief(d) for d in recalls],
            "active_recall": _brief(next((d for d in recalls if d.status == RECALL_ACTIVE), None)),
        }

    def _flow(self, d: DocumentHeader | None, movement_type: str, at) -> dict:
        info: ShipmentInfo | None = d.shipment_info if d is not None and d.doc_type == DOC_SHIP else None
        return {
            "document": _brief(d),
            "source": _brief(d.ref_document) if d is not None else None,
            "partner": _partner(d.partner) if d is not None else None,
            "movement_type": movement_type,
            "qty": ZERO,
            "at": at,
            "vehicle_no": info.vehicle_no if info else None,
            "driver_name": info.driver_name if info else None,
        }

    def _documents(self, ids: set) -> dict[uuid.UUID, DocumentHeader]:
        found: dict[uuid.UUID, DocumentHeader] = {}
        ids = list(ids)
        for i in range(0, len(ids), 1000):
            for d in self.db.scalars(select(DocumentHeader).where(DocumentHeader.id.in_(ids[i:i + 1000]))).unique():
                found[d.id] = d
        return found

    def _locations(self, ids: set) -> dict[uuid.UUID, Location]:
        found: dict[uuid.UUID, Location] = {}
        ids = list(ids)
        for i in range(0, len(ids), 1000):
            for loc in self.db.scalars(select(Location).where(Location.id.in_(ids[i:i + 1000]))):
                found[loc.id] = loc
        return found

    # ------------------------------------------------------------ from a document back to its batches

    def find_document(self, doc_no: str, permissions: set[str]) -> DocumentHeader:
        """A document by its number, of a type the user may read (a customer complaint names a delivery order)"""
        docs = self.db.scalars(
            select(DocumentHeader).where(
                DocumentHeader.tenant_id == self.tenant_id, DocumentHeader.doc_no == doc_no.strip(),
                DocumentHeader.is_deleted == false(),
            )
        ).unique()
        for d in docs:
            module = DOCUMENT_PERMISSIONS.get(d.doc_type, (None,))[0]
            if module and f"{module}.read" in permissions:
                return d
        raise NotFoundError(f"No document {doc_no.strip()} found")

    def document(self, document_id: uuid.UUID, permissions: set[str]) -> dict:
        d = self.db.get(DocumentHeader, document_id)
        module = DOCUMENT_PERMISSIONS.get(d.doc_type, (None,))[0] if d is not None else None
        if d is None or d.tenant_id != self.tenant_id or d.is_deleted or not module or f"{module}.read" not in permissions:
            raise NotFoundError("Document not found")

        grouped: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        items: dict[uuid.UUID, Item] = {}
        for line in d.lines:
            qty = line.qty_actual or line.qty_planned
            grouped[(line.item_id, line.batch_no, line.expiry_date)] += qty
            items[line.item_id] = line.item

        L, doc, line_ = StockLedger, DocumentHeader, DocumentLine
        batches = []
        for (item_id, batch_no, expiry_date), qty in grouped.items():
            entry = {
                "item": items[item_id], "batch_no": batch_no, "expiry_date": expiry_date, "qty": qty,
                "suppliers": [], "receipts": [], "other_customers": 0, "qty_on_hand": ZERO,
                "active_recall": _brief(active_recall(self.db, self.tenant_id, item_id, batch_no)),
            }
            if batch_no:
                by_doc = self.db.execute(
                    select(doc.id, L.movement_type)
                    .join(line_, line_.id == L.ref_document_line_id)
                    .join(doc, doc.id == line_.document_id)
                    .where(L.tenant_id == self.tenant_id, L.item_id == item_id, L.batch_no == batch_no,
                           L.movement_type.in_([MOVE_RECEIVE, MOVE_SHIP_OUT]))
                    .distinct()
                ).all()
                docs = self._documents({doc_id for doc_id, _ in by_doc})
                receipts = [docs[i] for i, t in by_doc if t == MOVE_RECEIVE]
                suppliers = {r.partner.id: r.partner for r in receipts if r.partner}
                customers = {docs[i].partner_id for i, t in by_doc if t == MOVE_SHIP_OUT and docs[i].partner_id}
                customers.discard(d.partner_id)
                entry.update(
                    suppliers=[{"id": p.id, "code": p.code, "name": p.name} for p in suppliers.values()],
                    receipts=[_brief(r) for r in sorted(receipts, key=lambda r: r.doc_no)],
                    other_customers=len(customers),
                    qty_on_hand=self.db.scalar(
                        select(func.coalesce(func.sum(StockBalance.qty_on_hand), 0)).where(
                            StockBalance.tenant_id == self.tenant_id, StockBalance.item_id == item_id,
                            StockBalance.batch_no == batch_no,
                        )
                    ) or ZERO,
                )
            batches.append(entry)
        batches.sort(key=lambda b: (b["item"].sku_code, b["batch_no"] or ""))
        return {
            "document": _brief(d),
            "partner": {"id": d.partner.id, "code": d.partner.code, "name": d.partner.name} if d.partner else None,
            "posted_at": d.posted_at,
            "batches": batches,
        }
