import uuid

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.document import DocumentHeader, DocumentLine
from app.schemas.document import PutawayIn
from app.services.document_common import (
    DOC_GRN,
    DOC_PUTAWAY,
    get_active_item,
    get_document,
    get_stock_location,
    get_uom,
    list_documents,
    next_doc_no,
    normalize_tracking,
    require_status,
    utcnow,
)
from app.services.grn_service import GRN_POSTED
from app.services.stock_service import (
    MOVE_PUTAWAY_IN,
    MOVE_PUTAWAY_OUT,
    Movement,
    apply_movements,
    to_base_qty,
)

PUTAWAY_DRAFT = "DRAFT"
PUTAWAY_POSTED = "POSTED"
PUTAWAY_CANCELLED = "CANCELLED"
PUTAWAY_TARGET_TYPES = ("BIN",)


class PutawayService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_PUTAWAY, **filters)

    def get(self, putaway_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_PUTAWAY, putaway_id, lock=lock)

    def create(self, data: PutawayIn) -> DocumentHeader:
        if data.ref_document_id is not None:
            grn = get_document(self.db, self.tenant_id, DOC_GRN, data.ref_document_id)
            require_status(grn, (GRN_POSTED,), "上架")

        lines = []
        for line_no, line_in in enumerate(data.lines, start=1):
            item = get_active_item(self.db, self.tenant_id, line_in.item_id)
            get_uom(self.db, self.tenant_id, line_in.uom_id)
            to_base_qty(self.db, self.tenant_id, item, line_in.uom_id, line_in.qty)
            self._validate_locations(line_in.from_location_id, line_in.to_location_id)
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
                    from_location_id=line_in.from_location_id,
                    to_location_id=line_in.to_location_id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )

        putaway = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_PUTAWAY,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_PUTAWAY),
            status=PUTAWAY_DRAFT,
            ref_document_id=data.ref_document_id,
            remark=data.remark,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        putaway.lines = lines
        self.db.add(putaway)
        self.db.flush()
        return self.get(putaway.id)

    def post(self, putaway_id: uuid.UUID) -> DocumentHeader:
        putaway = self.get(putaway_id, lock=True)
        require_status(putaway, (PUTAWAY_DRAFT,), "过账")

        movements = []
        for line in putaway.lines:
            self._validate_locations(line.from_location_id, line.to_location_id)
            base_qty = to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual)
            for location_id, qty, movement_type in (
                (line.from_location_id, -base_qty, MOVE_PUTAWAY_OUT),
                (line.to_location_id, base_qty, MOVE_PUTAWAY_IN),
            ):
                movements.append(
                    Movement(
                        item_id=line.item_id,
                        location_id=location_id,
                        batch_no=line.batch_no,
                        expiry_date=line.expiry_date,
                        qty_change=qty,
                        movement_type=movement_type,
                        ref_line_id=line.id,
                    )
                )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)

        putaway.status = PUTAWAY_POSTED
        putaway.posted_at = utcnow()
        putaway.updated_by = self.user_id
        putaway.row_version += 1
        self.db.flush()
        return putaway

    def cancel(self, putaway_id: uuid.UUID) -> DocumentHeader:
        putaway = self.get(putaway_id, lock=True)
        require_status(putaway, (PUTAWAY_DRAFT,), "取消")
        putaway.status = PUTAWAY_CANCELLED
        putaway.updated_by = self.user_id
        putaway.row_version += 1
        self.db.flush()
        return putaway

    def _validate_locations(self, from_location_id: uuid.UUID, to_location_id: uuid.UUID) -> None:
        if from_location_id == to_location_id:
            raise DomainError("来源仓位和目标仓位不能相同")
        get_stock_location(self.db, self.tenant_id, from_location_id)
        get_stock_location(self.db, self.tenant_id, to_location_id, PUTAWAY_TARGET_TYPES)
