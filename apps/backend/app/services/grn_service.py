import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.formatting import qty_text
from app.models.document import DocumentHeader, DocumentLine
from app.schemas.document import GrnIn
from app.services.document_common import (
    DOC_GRN,
    DOC_PO,
    FEATURE_ALLOW_OVER_RECEIPT,
    find_by_client_request,
    get_document,
    get_stock_location,
    is_feature_enabled,
    list_documents,
    next_doc_no,
    normalize_tracking,
    require_status,
    utcnow,
)
from app.services.purchase_order_service import (
    PO_PARTIALLY_RECEIVED,
    PO_RECEIVABLE,
    PO_RECEIVED,
)
from app.services.stock_service import MOVE_RECEIVE, Movement, apply_movements, to_base_qty

GRN_DRAFT = "DRAFT"
GRN_POSTED = "POSTED"
GRN_CANCELLED = "CANCELLED"


class GrnService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_GRN, **filters)

    def get(self, grn_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_GRN, grn_id, lock=lock)

    def create(self, data: GrnIn) -> DocumentHeader:
        # Must come before all validation: on a retry the PO may already be fully received by the previous request, and validating would report a false error
        existing = find_by_client_request(self.db, self.tenant_id, DOC_GRN, data.client_request_id)
        if existing is not None:
            return existing

        po = get_document(self.db, self.tenant_id, DOC_PO, data.po_id)
        require_status(po, PO_RECEIVABLE, "receive")
        location = get_stock_location(self.db, self.tenant_id, data.location_id)
        po_lines = {line.id: line for line in po.lines}

        lines = []
        requested: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        for line_no, line_in in enumerate(data.lines, start=1):
            po_line = po_lines.get(line_in.po_line_id)
            if po_line is None:
                raise DomainError(f"Line {line_no} does not belong to purchase order {po.doc_no}")
            batch_no, expiry_date = normalize_tracking(
                po_line.item, line_in.batch_no, line_in.expiry_date
            )
            requested[po_line.id] += line_in.qty
            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=line_no,
                    item_id=po_line.item_id,
                    uom_id=po_line.uom_id,
                    # Expected: the PO line's open quantity when the receipt was created, for reference only
                    qty_planned=max(po_line.qty_planned - po_line.qty_actual, Decimal(0)),
                    qty_actual=line_in.qty,
                    batch_no=batch_no,
                    expiry_date=expiry_date,
                    to_location_id=location.id,
                    ref_line_id=po_line.id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
        self._check_over_receipt(po_lines, requested)

        grn = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_GRN,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_GRN),
            status=GRN_DRAFT,
            partner_id=po.partner_id,
            ref_document_id=po.id,
            location_id=location.id,
            remark=data.remark,
            client_request_id=data.client_request_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        grn.lines = lines
        self.db.add(grn)
        self.db.flush()
        return self.get(grn.id)

    def post(self, grn_id: uuid.UUID) -> DocumentHeader:
        # Lock order is always GRN -> PO, so concurrent receipts of one PO queue on the PO lock
        grn = self.get(grn_id, lock=True)
        require_status(grn, (GRN_DRAFT,), "post")
        po = get_document(self.db, self.tenant_id, DOC_PO, grn.ref_document_id, lock=True)
        require_status(po, PO_RECEIVABLE, "receive")
        get_stock_location(self.db, self.tenant_id, grn.location_id)

        po_lines = {line.id: line for line in po.lines}
        requested: dict[uuid.UUID, Decimal] = defaultdict(Decimal)
        movements = []
        for line in grn.lines:
            # The item's batch/expiry settings may have changed since creation; validate again at posting
            batch_no, expiry_date = normalize_tracking(line.item, line.batch_no, line.expiry_date)
            requested[line.ref_line_id] += line.qty_actual
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=grn.location_id,
                    batch_no=batch_no,
                    expiry_date=expiry_date,
                    qty_change=to_base_qty(
                        self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual
                    ),
                    movement_type=MOVE_RECEIVE,
                    ref_line_id=line.id,
                )
            )
        self._check_over_receipt(po_lines, requested)

        for po_line_id, qty in requested.items():
            po_lines[po_line_id].qty_actual += qty
        fully_received = all(line.qty_actual >= line.qty_planned for line in po.lines)
        po.status = PO_RECEIVED if fully_received else PO_PARTIALLY_RECEIVED
        po.updated_by = self.user_id
        po.row_version += 1

        apply_movements(self.db, self.tenant_id, movements, self.user_id)

        grn.status = GRN_POSTED
        grn.posted_at = utcnow()
        grn.updated_by = self.user_id
        grn.row_version += 1
        self.db.flush()

        # Goods on the dock get a putaway sheet at once, to print and to work through on the PDA
        from app.services.transfer_service import PutawayService  # transfer_service imports this module

        PutawayService(self.db, self.tenant_id, self.user_id).create_sheet(grn)
        return grn

    def cancel(self, grn_id: uuid.UUID) -> DocumentHeader:
        grn = self.get(grn_id, lock=True)
        require_status(grn, (GRN_DRAFT,), "cancel")
        grn.status = GRN_CANCELLED
        grn.updated_by = self.user_id
        grn.row_version += 1
        self.db.flush()
        return grn

    def _check_over_receipt(
        self, po_lines: dict[uuid.UUID, DocumentLine], requested: dict[uuid.UUID, Decimal]
    ) -> None:
        if is_feature_enabled(self.db, self.tenant_id, FEATURE_ALLOW_OVER_RECEIPT):
            return
        for po_line_id, qty in requested.items():
            po_line = po_lines[po_line_id]
            if po_line.qty_actual + qty > po_line.qty_planned:
                raise DomainError(
                    f"Item {po_line.item.sku_code} over-received: ordered {qty_text(po_line.qty_planned)}, "
                    f"received {qty_text(po_line.qty_actual)}, this receipt {qty_text(qty)}"
                )
