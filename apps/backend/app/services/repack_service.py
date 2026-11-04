import uuid

from sqlalchemy.orm import Session

from app.models.document import DocumentHeader, DocumentLine
from app.schemas.extension import RepackIn, RepackLineIn
from app.services.document_common import (
    DOC_REPACK,
    find_by_client_request,
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
from app.services.stock_service import (
    MOVE_REPACK_IN,
    MOVE_REPACK_OUT,
    Movement,
    apply_movements,
    to_base_qty,
)

REPACK_DRAFT = "DRAFT"
REPACK_POSTED = "POSTED"
REPACK_CANCELLED = "CANCELLED"


class RepackService:
    """Repack (Ninso Repack): one document consumes source items and produces new ones, e.g. breaking cartons into units or kitting a gift box.
    Lines: from_location set = consumption line (taken from that location); to_location set = output line (put into that location).
    Quantities only, no cost allocation. Posting deducts and adds in one transaction; if any consumption line is short the whole document rolls back.
    """

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_REPACK, **filters)

    def get(self, document_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_REPACK, document_id, lock=lock)

    def create(self, data: RepackIn) -> DocumentHeader:
        existing = find_by_client_request(self.db, self.tenant_id, DOC_REPACK, data.client_request_id)
        if existing is not None:
            return existing
        lines = [self._line(l, consume=True) for l in data.inputs] + [
            self._line(l, consume=False) for l in data.outputs
        ]
        for line_no, line in enumerate(lines, start=1):
            line.line_no = line_no
        document = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_REPACK,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_REPACK),
            status=REPACK_DRAFT,
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
        require_status(document, (REPACK_DRAFT,), "post")
        movements = []
        for line in document.lines:
            consume = line.from_location_id is not None
            location_id = line.from_location_id if consume else line.to_location_id
            get_stock_location(self.db, self.tenant_id, location_id)
            qty = to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual)
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=-qty if consume else qty,
                    movement_type=MOVE_REPACK_OUT if consume else MOVE_REPACK_IN,
                    ref_line_id=line.id,
                )
            )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)
        document.status = REPACK_POSTED
        document.posted_at = utcnow()
        self._touch(document)
        self.db.flush()
        return document

    def cancel(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (REPACK_DRAFT,), "cancel")
        document.status = REPACK_CANCELLED
        self._touch(document)
        self.db.flush()
        return document

    def _line(self, line_in: RepackLineIn, consume: bool) -> DocumentLine:
        item = get_active_item(self.db, self.tenant_id, line_in.item_id)
        get_uom(self.db, self.tenant_id, line_in.uom_id)
        to_base_qty(self.db, self.tenant_id, item, line_in.uom_id, line_in.qty)
        get_stock_location(self.db, self.tenant_id, line_in.location_id)
        batch_no, expiry_date = normalize_tracking(item, line_in.batch_no, line_in.expiry_date)
        return DocumentLine(
            tenant_id=self.tenant_id,
            line_no=0,
            item_id=item.id,
            uom_id=line_in.uom_id,
            qty_planned=line_in.qty,
            qty_actual=line_in.qty,
            batch_no=batch_no,
            expiry_date=expiry_date,
            from_location_id=line_in.location_id if consume else None,
            to_location_id=None if consume else line_in.location_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )

    def _touch(self, document: DocumentHeader) -> None:
        document.updated_by = self.user_id
        document.row_version += 1
