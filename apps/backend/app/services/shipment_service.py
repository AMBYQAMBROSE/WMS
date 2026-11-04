import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.document import DocumentHeader, DocumentLine, ShipmentInfo
from app.schemas.outbound import ShipmentCreate, ShipmentInfoIn
from app.services.document_common import (
    DOC_PICK,
    DOC_SHIP,
    find_by_client_request,
    get_document,
    get_stock_location,
    list_documents,
    next_doc_no,
    require_status,
    utcnow,
)
from app.services.sales_order_service import (
    PICK_POSTED,
    SHIP_DRAFT,
    SHIP_POSTED,
    SO_IN_PROGRESS,
    SO_PARTIALLY_SHIPPED,
    SO_SHIPPED,
    SalesOrderService,
)
from app.services.stock_service import MOVE_SHIP_OUT, Movement, apply_movements

SHIP_CANCELLED = "CANCELLED"
ZERO = Decimal(0)


class ShipmentService:
    """Shipment (DO): takes everything picked but not yet shipped for the order from staging -> record vehicle/driver/seal -> post to ship out.
    An order can have only one unposted shipment at a time. Line from_location is the staging location, ref_line points to the order line.
    """

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.orders = SalesOrderService(db, tenant_id, user_id)

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_SHIP, **filters)

    def get(self, ship_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_SHIP, ship_id, lock=lock)

    def create(self, data: ShipmentCreate) -> DocumentHeader:
        existing = find_by_client_request(self.db, self.tenant_id, DOC_SHIP, data.client_request_id)
        if existing is not None:
            return existing
        so = self.orders.get(data.so_id, lock=True)
        require_status(so, (SO_IN_PROGRESS, SO_PARTIALLY_SHIPPED), "ship")
        if self.orders._has_draft_shipment(so.id):
            raise DomainError(f"Order {so.doc_no} already has an unposted shipment")

        staged = self._staged(so.id)
        so_lines = {line.id: line for line in so.lines}
        lines = []
        for (so_line_id, location_id, batch_no, expiry_date), qty in sorted(
            staged.items(), key=lambda kv: so_lines[kv[0][0]].line_no
        ):
            so_line = so_lines[so_line_id]
            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=len(lines) + 1,
                    item_id=so_line.item_id,
                    uom_id=so_line.item.base_uom_id,
                    qty_planned=qty,
                    qty_actual=qty,
                    batch_no=batch_no,
                    expiry_date=expiry_date,
                    from_location_id=location_id,
                    ref_line_id=so_line_id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
        if not lines:
            raise DomainError(f"Order {so.doc_no} has no picked goods waiting to ship")

        ship = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_SHIP,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_SHIP),
            status=SHIP_DRAFT,
            partner_id=so.partner_id,
            ref_document_id=so.id,
            client_request_id=data.client_request_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        ship.lines = lines
        ship.shipment_info = ShipmentInfo(**ShipmentInfoIn.model_validate(data.model_dump()).model_dump())
        self.db.add(ship)
        self.db.flush()
        return self.get(ship.id)

    def update_info(self, ship_id: uuid.UUID, data: ShipmentInfoIn) -> DocumentHeader:
        ship = self.get(ship_id, lock=True)
        require_status(ship, (SHIP_DRAFT,), "edit loading details")
        info = ship.shipment_info or ShipmentInfo()
        for key, value in data.model_dump().items():
            setattr(info, key, value)
        ship.shipment_info = info
        self._touch(ship)
        self.db.flush()
        return ship

    def post(self, ship_id: uuid.UUID) -> DocumentHeader:
        # Fixed lock order: shipment -> order
        ship = self.get(ship_id, lock=True)
        require_status(ship, (SHIP_DRAFT,), "post")
        so = self.orders.get(ship.ref_document_id, lock=True)
        require_status(so, (SO_IN_PROGRESS, SO_PARTIALLY_SHIPPED), "ship")

        movements = []
        shipped: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
        for line in ship.lines:
            get_stock_location(self.db, self.tenant_id, line.from_location_id)
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.from_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=-line.qty_actual,
                    movement_type=MOVE_SHIP_OUT,
                    ref_line_id=line.id,
                )
            )
            shipped[line.ref_line_id] += line.qty_actual
        apply_movements(self.db, self.tenant_id, movements, self.user_id)

        for so_line in so.lines:
            if so_line.id in shipped:
                so_line.qty_actual += shipped[so_line.id]
                so_line.updated_by = self.user_id
        self.db.flush()
        progress = self.orders.progress(so)
        done = all(p.shipped >= p.ordered for p in progress.values())
        so.status = SO_SHIPPED if done else SO_PARTIALLY_SHIPPED
        so.updated_by = self.user_id
        so.row_version += 1

        ship.status = SHIP_POSTED
        ship.posted_at = utcnow()
        self._touch(ship)
        self.db.flush()
        return ship

    def cancel(self, ship_id: uuid.UUID) -> DocumentHeader:
        ship = self.get(ship_id, lock=True)
        require_status(ship, (SHIP_DRAFT,), "cancel")
        ship.status = SHIP_CANCELLED
        self._touch(ship)
        self.db.flush()
        return ship

    def _staged(self, so_id: uuid.UUID) -> dict[tuple, Decimal]:
        """Picked but unshipped quantity of this order in staging: picked on posted picks minus shipped on posted shipments, grouped by (order line, staging location, batch, expiry)"""

        def sums(doc_type: str, location_col):
            return self.db.execute(
                select(
                    DocumentLine.ref_line_id,
                    location_col,
                    DocumentLine.batch_no,
                    DocumentLine.expiry_date,
                    func.sum(DocumentLine.qty_actual),
                )
                .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
                .where(
                    DocumentHeader.tenant_id == self.tenant_id,
                    DocumentHeader.doc_type == doc_type,
                    DocumentHeader.ref_document_id == so_id,
                    DocumentHeader.status == (PICK_POSTED if doc_type == DOC_PICK else SHIP_POSTED),
                    DocumentHeader.is_deleted == false(),
                )
                .group_by(
                    DocumentLine.ref_line_id, location_col, DocumentLine.batch_no, DocumentLine.expiry_date
                )
            )

        staged: dict[tuple, Decimal] = defaultdict(lambda: ZERO)
        for ref_line_id, location_id, batch_no, expiry_date, qty in sums(DOC_PICK, DocumentLine.to_location_id):
            staged[(ref_line_id, location_id, batch_no, expiry_date)] += qty
        for ref_line_id, location_id, batch_no, expiry_date, qty in sums(DOC_SHIP, DocumentLine.from_location_id):
            staged[(ref_line_id, location_id, batch_no, expiry_date)] -= qty
        return {key: qty for key, qty in staged.items() if qty > 0}

    def _touch(self, ship: DocumentHeader) -> None:
        ship.updated_by = self.user_id
        ship.row_version += 1
