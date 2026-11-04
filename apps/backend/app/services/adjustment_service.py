import uuid

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.document import DocumentHeader, DocumentLine
from app.models.reason_code import REASON_CATEGORY_ADJUST, ReasonCode
from app.schemas.document import AdjustmentIn
from app.services.document_common import (
    DOC_ADJUST,
    find_by_client_request,
    get_active_item,
    get_document,
    get_reason,
    get_stock_location,
    get_uom,
    list_documents,
    next_doc_no,
    normalize_tracking,
    require_status,
    utcnow,
)
from app.services.stock_service import (
    MOVE_ADJUST_IN,
    MOVE_ADJUST_OUT,
    Movement,
    apply_movements,
    to_base_qty,
)

ADJUST_DRAFT = "DRAFT"
ADJUST_POSTED = "POSTED"
ADJUST_CANCELLED = "CANCELLED"


class AdjustmentService:
    """Stock adjustment: create (any clerk) -> post (requires adjustment.post, i.e. approval).
    Line quantities are signed: positive adds, negative removes; a line's to_location is the adjusted location.
    """

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_ADJUST, **filters)

    def get(self, document_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_ADJUST, document_id, lock=lock)

    def create(self, data: AdjustmentIn) -> DocumentHeader:
        existing = find_by_client_request(self.db, self.tenant_id, DOC_ADJUST, data.client_request_id)
        if existing is not None:
            return existing
        self._get_reason(data.reason_code_id)

        lines = []
        for line_no, line_in in enumerate(data.lines, start=1):
            if line_in.qty == 0:
                raise DomainError(f"Line {line_no}: adjustment quantity cannot be 0")
            item = get_active_item(self.db, self.tenant_id, line_in.item_id)
            get_uom(self.db, self.tenant_id, line_in.uom_id)
            to_base_qty(self.db, self.tenant_id, item, line_in.uom_id, abs(line_in.qty))
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
                    to_location_id=line_in.location_id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )

        document = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_ADJUST,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_ADJUST),
            status=ADJUST_DRAFT,
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
        require_status(document, (ADJUST_DRAFT,), "post")
        self._get_reason(document.reason_code_id)

        movements = []
        for line in document.lines:
            # The location may have been locked, deactivated or put into a count since creation; validate again at posting
            get_stock_location(self.db, self.tenant_id, line.to_location_id)
            base_qty = to_base_qty(
                self.db, self.tenant_id, line.item, line.uom_id, abs(line.qty_actual)
            )
            increase = line.qty_actual > 0
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.to_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=base_qty if increase else -base_qty,
                    movement_type=MOVE_ADJUST_IN if increase else MOVE_ADJUST_OUT,
                    ref_line_id=line.id,
                )
            )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)

        document.status = ADJUST_POSTED
        document.posted_at = utcnow()
        document.updated_by = self.user_id
        document.row_version += 1
        self.db.flush()
        return document

    def cancel(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (ADJUST_DRAFT,), "cancel")
        document.status = ADJUST_CANCELLED
        document.updated_by = self.user_id
        document.row_version += 1
        self.db.flush()
        return document

    def _get_reason(self, reason_code_id: uuid.UUID | None) -> ReasonCode:
        return get_reason(self.db, self.tenant_id, reason_code_id, REASON_CATEGORY_ADJUST, "Adjustment reason")
