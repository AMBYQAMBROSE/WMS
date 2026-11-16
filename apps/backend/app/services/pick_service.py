import uuid
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.formatting import qty_text
from app.models.document import DocumentHeader, DocumentLine
from app.services.document_common import (
    DOC_PICK,
    DOC_SHIP,
    DOC_SO,
    get_document,
    get_stock_location,
    list_documents,
    require_status,
    utcnow,
)
from app.services.sales_order_service import (
    PICK_CANCELLED,
    PICK_OPEN,
    PICK_POSTED,
    PICK_REVERSED,
    SHIP_DRAFT,
    SHIP_POSTED,
)
from app.services.stock_service import (
    MOVE_PICK_IN,
    MOVE_PICK_OUT,
    MOVE_UNPICK_IN,
    MOVE_UNPICK_OUT,
    Movement,
    apply_movements,
)

ZERO = Decimal(0)


class PickService:
    """Pick list: created at allocation (OPEN, stock reserved) -> confirm picked quantity per line (short picks allowed) -> post:
    the bin decreases by the picked quantity and the line's whole reservation is released; the staging location increases by the picked quantity,
    reserved for the order until it ships. Cancelling only releases the reservation. A posted pick whose goods have not shipped can be
    reversed (the customer cancelled, the wrong goods were picked): the goods go back from staging to their bins.
    Line qty_planned is the allocated quantity and qty_actual the picked quantity, both base units; from_location is the bin, to_location the staging location.
    """

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_PICK, **filters)

    def get(self, pick_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_PICK, pick_id, lock=lock)

    def confirm_line(self, pick_id: uuid.UUID, line_id: uuid.UUID, qty: Decimal) -> DocumentHeader:
        pick = self.get(pick_id, lock=True)
        require_status(pick, (PICK_OPEN,), "confirm picks")
        line = next((l for l in pick.lines if l.id == line_id), None)
        if line is None:
            raise DomainError("Pick line not found")
        if qty > line.qty_planned:
            # Extra picked goods have no reservation and may belong to another order, so over-picking is not allowed
            raise DomainError(
                f"{line.item.sku_code} can pick at most {qty_text(line.qty_planned)} (allocated), got {qty_text(qty)}"
            )
        line.qty_actual = qty
        line.confirmed_at = utcnow()
        line.confirmed_by = self.user_id
        line.updated_by = self.user_id
        self._touch(pick)
        self.db.flush()
        # Only the foreign key changed; the loaded confirmer relationship is stale (often None), so reload it
        self.db.expire(line, ["confirmer"])
        return self.get(pick.id)

    def confirm_all(self, pick_id: uuid.UUID) -> DocumentHeader:
        """Confirm every unconfirmed line at its allocated quantity (used for whole-list confirmation on the web)"""
        pick = self.get(pick_id, lock=True)
        require_status(pick, (PICK_OPEN,), "confirm picks")
        now = utcnow()
        touched = []
        for line in pick.lines:
            if line.confirmed_at is None:
                line.qty_actual = line.qty_planned
                line.confirmed_at = now
                line.confirmed_by = self.user_id
                line.updated_by = self.user_id
                touched.append(line)
        self._touch(pick)
        self.db.flush()
        for line in touched:
            self.db.expire(line, ["confirmer"])
        return self.get(pick.id)

    def post(self, pick_id: uuid.UUID) -> DocumentHeader:
        pick = self.get(pick_id, lock=True)
        require_status(pick, (PICK_OPEN,), "post")
        pending = [l for l in pick.lines if l.confirmed_at is None]
        if pending:
            listed = ", ".join(f"{l.from_location.code} {l.item.sku_code}" for l in pending[:5])
            raise DomainError(f"{len(pending)} lines not confirmed yet: {listed}")

        get_stock_location(self.db, self.tenant_id, pick.location_id, ("DOCK",))
        movements = []
        for line in pick.lines:
            # Stock cannot leave a locked bin or a bin being counted
            get_stock_location(self.db, self.tenant_id, line.from_location_id)
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.from_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=-line.qty_actual,
                    movement_type=MOVE_PICK_OUT,
                    ref_line_id=line.id,
                    # Release the whole line's reservation however much was picked: the short quantity returns to the order as unallocated and can be allocated again
                    allocated_change=-line.qty_planned,
                )
            )
            if line.qty_actual > 0:
                movements.append(
                    Movement(
                        item_id=line.item_id,
                        location_id=line.to_location_id,
                        batch_no=line.batch_no,
                        expiry_date=line.expiry_date,
                        qty_change=line.qty_actual,
                        movement_type=MOVE_PICK_IN,
                        ref_line_id=line.id,
                        # Staged goods belong to this order until they ship: nothing else may move or allocate them
                        allocated_change=line.qty_actual,
                    )
                )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)
        pick.status = PICK_POSTED
        pick.posted_at = utcnow()
        self._touch(pick)
        self.db.flush()
        return pick

    def cancel(self, pick_id: uuid.UUID) -> DocumentHeader:
        pick = self.get(pick_id, lock=True)
        require_status(pick, (PICK_OPEN,), "cancel")
        apply_movements(
            self.db,
            self.tenant_id,
            [
                Movement(
                    item_id=line.item_id,
                    location_id=line.from_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=ZERO,
                    movement_type=MOVE_PICK_OUT,
                    ref_line_id=line.id,
                    allocated_change=-line.qty_planned,
                )
                for line in pick.lines
            ],
            self.user_id,
        )
        pick.status = PICK_CANCELLED
        self._touch(pick)
        self.db.flush()
        return pick

    def reverse(self, pick_id: uuid.UUID) -> DocumentHeader:
        """Return the goods of a posted pick from staging to the bins they came from. The order then counts them as
        unallocated again, so it can be allocated anew, closed or cancelled. Only while the goods are still in staging:
        not shipped and not on a shipment being loaded."""
        # Lock order: pick -> order (as shipments do: shipment -> order), so shipping and reversing cannot overlap
        pick = self.get(pick_id, lock=True)
        require_status(pick, (PICK_POSTED,), "return to stock")
        so = get_document(self.db, self.tenant_id, DOC_SO, pick.ref_document_id, lock=True)
        loading = self.db.scalar(
            select(DocumentHeader.doc_no).where(
                DocumentHeader.tenant_id == self.tenant_id,
                DocumentHeader.doc_type == DOC_SHIP,
                DocumentHeader.ref_document_id == so.id,
                DocumentHeader.status == SHIP_DRAFT,
                DocumentHeader.is_deleted == false(),
            )
        )
        if loading is not None:
            raise DomainError(f"Shipment {loading} of order {so.doc_no} is being loaded; post or cancel it first")

        # A shipment takes everything in staging for the order, so this pick's goods are either all still there or all gone
        staged: dict[uuid.UUID, Decimal] = defaultdict(lambda: ZERO)
        for status, doc_type in ((PICK_POSTED, DOC_PICK), (SHIP_POSTED, DOC_SHIP)):
            rows = self.db.execute(
                select(DocumentLine.ref_line_id, func.sum(DocumentLine.qty_actual))
                .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
                .where(
                    DocumentHeader.tenant_id == self.tenant_id,
                    DocumentHeader.doc_type == doc_type,
                    DocumentHeader.ref_document_id == so.id,
                    DocumentHeader.status == status,
                    DocumentHeader.is_deleted == false(),
                )
                .group_by(DocumentLine.ref_line_id)
            )
            for so_line_id, qty in rows:
                staged[so_line_id] += qty if doc_type == DOC_PICK else -qty

        movements = []
        for line in pick.lines:
            if line.qty_actual <= 0:
                continue
            staged[line.ref_line_id] -= line.qty_actual
            if staged[line.ref_line_id] < 0:
                raise DomainError(
                    f"The goods of pick list {pick.doc_no} have already shipped ({line.item.sku_code}); "
                    "record a customer return instead"
                )
            get_stock_location(self.db, self.tenant_id, line.to_location_id)
            get_stock_location(self.db, self.tenant_id, line.from_location_id)
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.to_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=-line.qty_actual,
                    movement_type=MOVE_UNPICK_OUT,
                    ref_line_id=line.id,
                    allocated_change=-line.qty_actual,
                )
            )
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.from_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=line.qty_actual,
                    movement_type=MOVE_UNPICK_IN,
                    ref_line_id=line.id,
                )
            )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)
        pick.status = PICK_REVERSED
        self._touch(pick)
        so.updated_by = self.user_id
        so.row_version += 1
        self.db.flush()
        return pick

    def _touch(self, pick: DocumentHeader) -> None:
        pick.updated_by = self.user_id
        pick.row_version += 1
