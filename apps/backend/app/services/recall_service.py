"""Batch recall: one click holds a batch everywhere, drafts its move to quarantine and lists who received it.

A recall is a document (doc type RECALL, one line: item + batch) so it gets a number, a history, live updates and the
usual permissions. While it is ACTIVE the batch is held (app/services/batch_hold.py): never allocated, never shipped.
Releasing it ends the hold. The line keeps what the batch looked like when the recall started: qty_planned is the
quantity on hand, qty_actual the quantity already shipped to customers.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError
from app.models.document import DocumentHeader, DocumentLine
from app.models.item import Item
from app.models.location import STOCK_LOCATION_TYPES
from app.models.stock import StockBalance
from app.schemas.document import TransferIn, TransferLineIn
from app.schemas.trace import RecallIn
from app.services.batch_hold import RECALL_ACTIVE, RECALL_RELEASED, active_recall
from app.services.document_common import (
    DOC_MOVE,
    DOC_RECALL,
    active_count_for_location,
    find_by_client_request,
    get_document,
    get_stock_location,
    list_documents,
    next_doc_no,
    require_status,
    utcnow,
)
from app.services.trace_service import TraceService
from app.services.transfer_service import MoveService

ZERO = Decimal(0)


@dataclass
class RecallService:
    db: Session
    tenant_id: uuid.UUID
    user_id: uuid.UUID

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_RECALL, **filters)

    def get(self, recall_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_RECALL, recall_id, lock=lock)

    def detail(self, recall_id: uuid.UUID, skipped: list[dict] | None = None) -> dict:
        recall = self.get(recall_id)
        line = recall.lines[0]
        moves = list(
            self.db.scalars(
                select(DocumentHeader)
                .where(DocumentHeader.tenant_id == self.tenant_id, DocumentHeader.doc_type == DOC_MOVE,
                       DocumentHeader.ref_document_id == recall.id, DocumentHeader.is_deleted == false())
                .order_by(DocumentHeader.created_at)
            ).unique()
        )
        return {
            "document": recall,
            "moves": moves,
            "skipped": skipped or [],
            "trace": TraceService(self.db, self.tenant_id).trace(line.item_id, line.batch_no),
        }

    def create(self, data: RecallIn) -> dict:
        existing = find_by_client_request(self.db, self.tenant_id, DOC_RECALL, data.client_request_id)
        if existing is not None:
            return self.detail(existing.id)

        item = self.db.get(Item, data.item_id)
        if item is None or item.tenant_id != self.tenant_id or item.is_deleted:
            raise DomainError("Item not found")
        batch_no = data.batch_no.strip()
        current = active_recall(self.db, self.tenant_id, item.id, batch_no)
        if current is not None:
            raise ConflictError(f"Batch {batch_no} of {item.sku_code} is already being recalled ({current.doc_no})")
        quarantine = (
            get_stock_location(self.db, self.tenant_id, data.quarantine_location_id, STOCK_LOCATION_TYPES)
            if data.quarantine_location_id else None
        )
        # Raises when the batch has never been in stock: a typo must not hold nothing and look like it worked
        trace = TraceService(self.db, self.tenant_id).trace(item.id, batch_no)

        recall = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_RECALL,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_RECALL),
            status=RECALL_ACTIVE,
            location_id=quarantine.id if quarantine else None,
            remark=data.reason.strip(),
            client_request_id=data.client_request_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        recall.lines = [
            DocumentLine(
                tenant_id=self.tenant_id,
                line_no=1,
                item_id=item.id,
                uom_id=item.base_uom_id,
                qty_planned=trace["summary"]["qty_on_hand"],
                qty_actual=trace["summary"]["shipped"],
                batch_no=batch_no,
                created_by=self.user_id,
                updated_by=self.user_id,
            )
        ]
        self.db.add(recall)
        self.db.flush()

        skipped = self._quarantine(recall, item, batch_no, quarantine) if quarantine else []
        return self.detail(recall.id, skipped)

    def _quarantine(self, recall: DocumentHeader, item: Item, batch_no: str, quarantine) -> list[dict]:
        """Draft a move of everything that can move now; report the rest (allocated, locked, being counted)"""
        balances = list(
            self.db.scalars(
                select(StockBalance)
                .where(StockBalance.tenant_id == self.tenant_id, StockBalance.item_id == item.id,
                       StockBalance.batch_no == batch_no, StockBalance.qty_on_hand > 0,
                       StockBalance.location_id != quarantine.id)
                .order_by(StockBalance.created_at)
            ).unique()
        )
        lines, skipped = [], []
        for b in balances:
            free = b.qty_on_hand - b.qty_allocated
            if b.qty_allocated > 0:
                where = "picked, waiting in staging" if b.location.location_type == "DOCK" else "allocated to pick lists"
                skipped.append({"location": b.location, "qty": b.qty_allocated,
                                "reason": f"{where}: return it to stock, then move it"})
            if free <= 0:
                continue
            reason = None
            if not b.location.is_active:
                reason = "location is inactive"
            elif b.location.is_locked:
                reason = "location is locked"
            elif (count := active_count_for_location(self.db, self.tenant_id, b.location_id)) is not None:
                reason = f"location is being counted ({count.doc_no})"
            if reason:
                skipped.append({"location": b.location, "qty": free, "reason": reason})
                continue
            lines.append(TransferLineIn(
                item_id=item.id, uom_id=item.base_uom_id, qty=free, batch_no=batch_no, expiry_date=b.expiry_date,
                from_location_id=b.location_id, to_location_id=quarantine.id,
            ))
        if lines:
            MoveService(self.db, self.tenant_id, self.user_id).create(TransferIn(
                ref_document_id=recall.id,
                remark=f"Recall {recall.doc_no}: move batch {batch_no} to quarantine {quarantine.code}",
                lines=lines,
            ))
        return skipped

    def release(self, recall_id: uuid.UUID) -> dict:
        recall = self.get(recall_id, lock=True)
        require_status(recall, (RECALL_ACTIVE,), "release")
        recall.status = RECALL_RELEASED
        recall.posted_at = utcnow()
        recall.updated_by = self.user_id
        recall.row_version += 1
        self.db.flush()
        return self.detail(recall.id)

    def customers(self, recall_id: uuid.UUID) -> list[dict]:
        """One row per shipment that took the batch out: who to notify, with what to tell them"""
        recall = self.get(recall_id)
        line = recall.lines[0]
        trace = TraceService(self.db, self.tenant_id).trace(line.item_id, line.batch_no)
        rows = []
        for flow in trace["outbound"]:
            if flow["movement_type"] != "SHIP_OUT":
                continue
            partner = flow["partner"] or {}
            rows.append({
                "customer_code": partner.get("code"), "customer_name": partner.get("name"),
                "contact_name": partner.get("contact_name"), "contact_phone": partner.get("contact_phone"),
                "address": partner.get("address"),
                "shipment_no": flow["document"]["doc_no"] if flow["document"] else None,
                "sales_order_no": flow["source"]["doc_no"] if flow["source"] else None,
                "shipped_at": flow["at"], "qty": flow["qty"], "unit": trace["item"].base_uom.code,
                "vehicle_no": flow["vehicle_no"], "sku_code": trace["item"].sku_code, "item_name": trace["item"].name,
                "batch_no": line.batch_no,
            })
        return rows

