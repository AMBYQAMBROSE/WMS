import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError
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
    get_uom,
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
QTY_STEP = Decimal("0.0001")  # quantities are stored with 4 decimals


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
            if existing.ref_document_id != data.po_id:
                # A retry repeats the same receipt. The same ID for another order is a client bug: answering with the
                # old receipt would let the client believe this one was saved
                raise ConflictError(f"Request ID already used by document {existing.doc_no}")
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
            uom_id = get_uom(self.db, self.tenant_id, line_in.uom_id).id if line_in.uom_id else po_line.uom_id
            requested[po_line.id] += self._in_order_unit(po_line, uom_id, line_in.qty)
            open_qty = max(po_line.qty_planned - po_line.qty_actual, Decimal(0))
            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=line_no,
                    item_id=po_line.item_id,
                    uom_id=uom_id,
                    # Expected: the PO line's open quantity when the receipt was created (in this line's unit), for reference only
                    qty_planned=self._from_order_unit(po_line, uom_id, open_qty),
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
            requested[line.ref_line_id] += self._in_order_unit(po_lines[line.ref_line_id], line.uom_id, line.qty_actual)
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
                unit = po_line.uom.code
                raise DomainError(
                    f"Item {po_line.item.sku_code} over-received: ordered {qty_text(po_line.qty_planned)} {unit}, "
                    f"received {qty_text(po_line.qty_actual)} {unit}, this receipt {qty_text(qty)} {unit}"
                )

    def _in_order_unit(self, po_line: DocumentLine, uom_id: uuid.UUID, qty: Decimal) -> Decimal:
        """A received quantity in the order line's unit, which the order's progress is kept in (e.g. 2 PLT -> 960 EA).
        Refused when it does not come out exact, such as 5 EA against an order in cartons of 12."""
        if uom_id == po_line.uom_id:
            return qty
        item = po_line.item
        converted = to_base_qty(self.db, self.tenant_id, item, uom_id, qty) / to_base_qty(
            self.db, self.tenant_id, item, po_line.uom_id, Decimal(1)
        )
        if converted != converted.quantize(QTY_STEP):
            unit = get_uom(self.db, self.tenant_id, uom_id).code
            raise DomainError(
                f"Item {item.sku_code}: {qty_text(qty)} {unit} does not come to an exact quantity of the order unit "
                f"{po_line.uom.code}; receive it in {po_line.uom.code} or a larger unit"
            )
        return converted.quantize(QTY_STEP)

    def _from_order_unit(self, po_line: DocumentLine, uom_id: uuid.UUID, qty: Decimal) -> Decimal:
        """An order-unit quantity shown in another unit, rounded (reference figures only)"""
        if uom_id == po_line.uom_id:
            return qty
        item = po_line.item
        base = to_base_qty(self.db, self.tenant_id, item, po_line.uom_id, qty)
        return (base / to_base_qty(self.db, self.tenant_id, item, uom_id, Decimal(1))).quantize(QTY_STEP)
