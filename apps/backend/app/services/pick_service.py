import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.formatting import qty_text
from app.models.document import DocumentHeader
from app.services.document_common import (
    DOC_PICK,
    get_document,
    get_stock_location,
    list_documents,
    require_status,
    utcnow,
)
from app.services.sales_order_service import PICK_CANCELLED, PICK_OPEN, PICK_POSTED
from app.services.stock_service import MOVE_PICK_IN, MOVE_PICK_OUT, Movement, apply_movements

ZERO = Decimal(0)


class PickService:
    """Pick list: created at allocation (OPEN, stock reserved) -> confirm picked quantity per line (short picks allowed) -> post:
    the bin decreases by the picked quantity and the line's whole reservation is released; the staging location increases by the picked quantity. Cancelling only releases the reservation.
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

    def _touch(self, pick: DocumentHeader) -> None:
        pick.updated_by = self.user_id
        pick.row_version += 1
