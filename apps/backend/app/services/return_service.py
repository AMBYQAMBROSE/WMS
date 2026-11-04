import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.document import DocumentHeader, DocumentLine
from app.models.reason_code import REASON_CATEGORY_RETURN
from app.schemas.extension import ReturnInIn, ReturnOutIn
from app.services.document_common import (
    DOC_PO,
    DOC_RETURN_IN,
    DOC_RETURN_OUT,
    DOC_SO,
    find_by_client_request,
    get_active_item,
    get_customer,
    get_document,
    get_reason,
    get_stock_location,
    get_supplier,
    get_uom,
    list_documents,
    next_doc_no,
    normalize_tracking,
    require_status,
    utcnow,
)
from app.services.purchase_order_service import PO_CLOSED, PO_PARTIALLY_RECEIVED, PO_RECEIVED
from app.services.sales_order_service import (
    RETURN_CANCELLED,
    RETURN_DRAFT,
    RETURN_POSTED,
    SO_CLOSED,
    SO_PARTIALLY_SHIPPED,
    SO_SHIPPED,
    SalesOrderService,
)
from app.services.stock_service import (
    MOVE_RETURN_IN,
    MOVE_RETURN_OUT,
    Movement,
    apply_movements,
    to_base_qty,
)

ZERO = Decimal(0)
SO_RETURNABLE = (SO_PARTIALLY_SHIPPED, SO_SHIPPED, SO_CLOSED)
PO_RETURNABLE = (PO_PARTIALLY_RECEIVED, PO_RECEIVED, PO_CLOSED)


class _ReturnBase:
    doc_type: str

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, self.doc_type, **filters)

    def get(self, document_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, self.doc_type, document_id, lock=lock)

    def cancel(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (RETURN_DRAFT,), "cancel")
        document.status = RETURN_CANCELLED
        self._touch(document)
        self.db.flush()
        return document

    def _reason(self, reason_code_id: uuid.UUID) -> None:
        get_reason(self.db, self.tenant_id, reason_code_id, REASON_CATEGORY_RETURN, "Return reason")

    def _finish_post(self, document: DocumentHeader) -> DocumentHeader:
        document.status = RETURN_POSTED
        document.posted_at = utcnow()
        self._touch(document)
        self.db.flush()
        return document

    def _touch(self, document: DocumentHeader) -> None:
        document.updated_by = self.user_id
        document.row_version += 1


class ReturnInService(_ReturnBase):
    """Customer return into stock (Ninso ReturnNote / GoodReturn).
    Each line has a disposition: RESTOCK puts good goods into a given location (resaleable); SCRAP records damaged goods without stocking them.
    When linked to the original sales order, cumulative returns per order line cannot exceed the shipped quantity.
    Lines: to_location = restock location (empty for scrap), ref_line = original order line.
    """

    doc_type = DOC_RETURN_IN

    def create(self, data: ReturnInIn) -> DocumentHeader:
        existing = find_by_client_request(self.db, self.tenant_id, self.doc_type, data.client_request_id)
        if existing is not None:
            return existing
        get_customer(self.db, self.tenant_id, data.partner_id)
        self._reason(data.reason_code_id)

        so = None
        if data.ref_document_id is not None:
            so = get_document(self.db, self.tenant_id, DOC_SO, data.ref_document_id)
            if so.partner_id != data.partner_id:
                raise DomainError(f"The return's customer differs from the customer of order {so.doc_no}")
            require_status(so, SO_RETURNABLE, "create a return (the order has not shipped)")

        lines = []
        for line_no, line_in in enumerate(data.lines, start=1):
            item = get_active_item(self.db, self.tenant_id, line_in.item_id)
            get_uom(self.db, self.tenant_id, line_in.uom_id)
            to_base_qty(self.db, self.tenant_id, item, line_in.uom_id, line_in.qty)

            so_line_id = None
            if so is not None:
                so_line = (
                    next((l for l in so.lines if l.id == line_in.ref_line_id), None)
                    if line_in.ref_line_id
                    else next((l for l in so.lines if l.item_id == item.id), None)
                )
                if so_line is None or so_line.item_id != item.id:
                    raise DomainError(f"Item {item.sku_code} is not on order {so.doc_no}")
                so_line_id = so_line.id

            if line_in.disposition == "RESTOCK":
                if line_in.location_id is None:
                    raise DomainError(f"Line {line_no} is set to restock; choose a restock location")
                location_id = get_stock_location(self.db, self.tenant_id, line_in.location_id).id
                batch_no, expiry_date = normalize_tracking(item, line_in.batch_no, line_in.expiry_date)
            else:
                # Scrapped goods do not enter stock; batch/expiry are informational and not enforced
                location_id = None
                batch_no, expiry_date = (line_in.batch_no or "").strip() or None, line_in.expiry_date

            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=line_no,
                    item_id=item.id,
                    uom_id=line_in.uom_id,
                    qty_planned=line_in.qty,
                    qty_actual=line_in.qty,
                    batch_no=batch_no,
                    expiry_date=expiry_date,
                    to_location_id=location_id,
                    ref_line_id=so_line_id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
        if so is not None:
            self._check_returnable(so, lines)

        document = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=self.doc_type,
            doc_no=next_doc_no(self.db, self.tenant_id, self.doc_type),
            status=RETURN_DRAFT,
            partner_id=data.partner_id,
            ref_document_id=data.ref_document_id,
            reason_code_id=data.reason_code_id,
            remark=data.remark,
            client_request_id=data.client_request_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        document.lines = lines
        self.db.add(document)
        self.db.flush()
        return self.get(document.id)

    def post(self, document_id: uuid.UUID) -> DocumentHeader:
        # Lock order: return -> original order. Two returns of the same order posting at once queue on the order lock and cannot over-return together
        document = self.get(document_id, lock=True)
        require_status(document, (RETURN_DRAFT,), "post")
        if document.ref_document_id is not None:
            so = get_document(self.db, self.tenant_id, DOC_SO, document.ref_document_id, lock=True)
            self._check_returnable(so, document.lines)

        movements = []
        for line in document.lines:
            if line.to_location_id is None:
                continue
            get_stock_location(self.db, self.tenant_id, line.to_location_id)
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.to_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual),
                    movement_type=MOVE_RETURN_IN,
                    ref_line_id=line.id,
                )
            )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)
        return self._finish_post(document)

    def _check_returnable(self, so: DocumentHeader, lines: list[DocumentLine]) -> None:
        """Cumulative returns (posted + this one) cannot exceed the shipped quantity, compared per order line in base units"""
        progress = SalesOrderService(self.db, self.tenant_id, self.user_id).progress(so)
        requested: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
        items = {}
        for line in lines:
            item = line.item if line.item is not None else get_active_item(self.db, self.tenant_id, line.item_id)
            items[line.ref_line_id] = item
            requested[line.ref_line_id] += to_base_qty(self.db, self.tenant_id, item, line.uom_id, line.qty_actual)
        for so_line_id, qty in requested.items():
            p = progress[so_line_id]
            if p.returned + qty > p.shipped:
                raise DomainError(
                    f"{items[so_line_id].sku_code} exceeds the returnable quantity: shipped {p.shipped.normalize()}, "
                    f"already returned {p.returned.normalize()}, this return {qty.normalize()}"
                )


class ReturnOutService(_ReturnBase):
    """Return to supplier (Ninso ReturnSupplier): stock out of a given location. Can be linked to the original purchase order.
    Lines: from_location = location to take stock from. Available stock is checked (stock allocated to orders cannot be returned).
    """

    doc_type = DOC_RETURN_OUT

    def create(self, data: ReturnOutIn) -> DocumentHeader:
        existing = find_by_client_request(self.db, self.tenant_id, self.doc_type, data.client_request_id)
        if existing is not None:
            return existing
        get_supplier(self.db, self.tenant_id, data.partner_id)
        self._reason(data.reason_code_id)
        if data.ref_document_id is not None:
            po = get_document(self.db, self.tenant_id, DOC_PO, data.ref_document_id)
            if po.partner_id != data.partner_id:
                raise DomainError(f"The return's supplier differs from the supplier of purchase order {po.doc_no}")
            require_status(po, PO_RETURNABLE, "create a return (the purchase order has not been received)")

        lines = []
        for line_no, line_in in enumerate(data.lines, start=1):
            item = get_active_item(self.db, self.tenant_id, line_in.item_id)
            get_uom(self.db, self.tenant_id, line_in.uom_id)
            to_base_qty(self.db, self.tenant_id, item, line_in.uom_id, line_in.qty)
            get_stock_location(self.db, self.tenant_id, line_in.location_id)
            batch_no, expiry_date = normalize_tracking(item, line_in.batch_no, line_in.expiry_date)
            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=line_no,
                    item_id=item.id,
                    uom_id=line_in.uom_id,
                    qty_planned=line_in.qty,
                    qty_actual=line_in.qty,
                    batch_no=batch_no,
                    expiry_date=expiry_date,
                    from_location_id=line_in.location_id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )

        document = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=self.doc_type,
            doc_no=next_doc_no(self.db, self.tenant_id, self.doc_type),
            status=RETURN_DRAFT,
            partner_id=data.partner_id,
            ref_document_id=data.ref_document_id,
            reason_code_id=data.reason_code_id,
            remark=data.remark,
            client_request_id=data.client_request_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        document.lines = lines
        self.db.add(document)
        self.db.flush()
        return self.get(document.id)

    def post(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (RETURN_DRAFT,), "post")
        movements = []
        for line in document.lines:
            get_stock_location(self.db, self.tenant_id, line.from_location_id)
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.from_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=-to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual),
                    movement_type=MOVE_RETURN_OUT,
                    ref_line_id=line.id,
                )
            )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)
        return self._finish_post(document)
