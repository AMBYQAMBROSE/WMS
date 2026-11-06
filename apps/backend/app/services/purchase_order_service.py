import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.document import DocumentHeader, DocumentLine
from app.repositories.base import check_version
from app.schemas.document import PurchaseOrderIn, PurchaseOrderLineIn
from app.services.document_common import (
    DOC_PO,
    get_active_item,
    get_document,
    get_supplier,
    get_uom,
    list_documents,
    next_doc_no,
    require_status,
)
from app.services.stock_service import to_base_qty

PO_DRAFT = "DRAFT"
PO_CONFIRMED = "CONFIRMED"
PO_PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
PO_RECEIVED = "RECEIVED"
PO_CLOSED = "CLOSED"
PO_CANCELLED = "CANCELLED"
PO_RECEIVABLE = (PO_CONFIRMED, PO_PARTIALLY_RECEIVED)


class PurchaseOrderService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_PO, **filters)

    def get(self, po_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_PO, po_id, lock=lock)

    def create(self, data: PurchaseOrderIn) -> DocumentHeader:
        get_supplier(self.db, self.tenant_id, data.partner_id)
        lines = self._build_lines(data.lines)
        po = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_PO,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_PO),
            status=PO_DRAFT,
            partner_id=data.partner_id,
            expected_date=data.expected_date,
            remark=data.remark,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        po.lines = lines
        self.db.add(po)
        self.db.flush()
        return self.get(po.id)

    def update(self, po_id: uuid.UUID, data: PurchaseOrderIn) -> DocumentHeader:
        po = self.get(po_id, lock=True)
        check_version(po, data.row_version, f"Purchase order {po.doc_no}")
        require_status(po, (PO_DRAFT,), "edit")
        get_supplier(self.db, self.tenant_id, data.partner_id)
        new_lines = self._build_lines(data.lines)

        po.partner_id = data.partner_id
        po.expected_date = data.expected_date
        po.remark = data.remark
        # Delete old lines before inserting new ones, otherwise the (document_id, line_no) unique constraint conflicts
        po.lines.clear()
        self.db.flush()
        po.lines.extend(new_lines)
        self._touch(po)
        self.db.flush()
        return self.get(po.id)

    def confirm(self, po_id: uuid.UUID) -> DocumentHeader:
        return self._transition(po_id, (PO_DRAFT,), PO_CONFIRMED, "confirm")

    def cancel(self, po_id: uuid.UUID) -> DocumentHeader:
        return self._transition(po_id, (PO_DRAFT, PO_CONFIRMED), PO_CANCELLED, "cancel")

    def close(self, po_id: uuid.UUID) -> DocumentHeader:
        """Manually close after partial receipt instead of waiting for the rest."""
        return self._transition(po_id, (PO_PARTIALLY_RECEIVED,), PO_CLOSED, "close")

    def _transition(
        self, po_id: uuid.UUID, allowed: tuple[str, ...], target: str, action: str
    ) -> DocumentHeader:
        po = self.get(po_id, lock=True)
        require_status(po, allowed, action)
        po.status = target
        self._touch(po)
        self.db.flush()
        return po

    def _build_lines(self, lines_in: list[PurchaseOrderLineIn]) -> list[DocumentLine]:
        lines = []
        for line_no, line in enumerate(lines_in, start=1):
            item = get_active_item(self.db, self.tenant_id, line.item_id)
            get_uom(self.db, self.tenant_id, line.uom_id)
            # Check unit conversions when ordering rather than finding out at receipt
            to_base_qty(self.db, self.tenant_id, item, line.uom_id, line.qty)
            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=line_no,
                    item_id=item.id,
                    uom_id=line.uom_id,
                    qty_planned=line.qty,
                    qty_actual=Decimal(0),
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
        return lines

    def _touch(self, po: DocumentHeader) -> None:
        po.updated_by = self.user_id
        po.row_version += 1
