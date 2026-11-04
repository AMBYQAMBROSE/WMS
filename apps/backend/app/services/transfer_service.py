import uuid

from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.document import DocumentHeader, DocumentLine
from app.models.location import STOCK_LOCATION_TYPES
from app.schemas.document import TransferIn
from app.services.document_common import (
    DOC_GRN,
    DOC_MOVE,
    DOC_PUTAWAY,
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
from app.services.grn_service import GRN_POSTED
from app.services.stock_service import (
    MOVE_MOVE_IN,
    MOVE_MOVE_OUT,
    MOVE_PUTAWAY_IN,
    MOVE_PUTAWAY_OUT,
    Movement,
    apply_movements,
    to_base_qty,
)

TRANSFER_DRAFT = "DRAFT"
TRANSFER_POSTED = "POSTED"
TRANSFER_CANCELLED = "CANCELLED"


class TransferService:
    """Shared logic for documents moving stock between locations (putaway, move): create -> post (source decreases, target increases) -> cancel.
    Subclasses only define the document type, allowed target location types, movement types and source document rules.
    """

    doc_type: str
    target_types: tuple[str, ...]
    movement_out: str
    movement_in: str

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, self.doc_type, **filters)

    def get(self, document_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, self.doc_type, document_id, lock=lock)

    def validate_ref_document(self, ref_document_id: uuid.UUID | None) -> None:
        if ref_document_id is not None:
            raise DomainError("This document type does not support a source document")

    def create(self, data: TransferIn) -> DocumentHeader:
        existing = find_by_client_request(self.db, self.tenant_id, self.doc_type, data.client_request_id)
        if existing is not None:
            return existing
        self.validate_ref_document(data.ref_document_id)

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

        document = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=self.doc_type,
            doc_no=next_doc_no(self.db, self.tenant_id, self.doc_type),
            status=TRANSFER_DRAFT,
            ref_document_id=data.ref_document_id,
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
        require_status(document, (TRANSFER_DRAFT,), "post")

        movements = []
        for line in document.lines:
            self._validate_locations(line.from_location_id, line.to_location_id)
            base_qty = to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual)
            for location_id, qty, movement_type in (
                (line.from_location_id, -base_qty, self.movement_out),
                (line.to_location_id, base_qty, self.movement_in),
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

        document.status = TRANSFER_POSTED
        document.posted_at = utcnow()
        document.updated_by = self.user_id
        document.row_version += 1
        self.db.flush()
        return document

    def cancel(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (TRANSFER_DRAFT,), "cancel")
        document.status = TRANSFER_CANCELLED
        document.updated_by = self.user_id
        document.row_version += 1
        self.db.flush()
        return document

    def _validate_locations(self, from_location_id: uuid.UUID, to_location_id: uuid.UUID) -> None:
        if from_location_id == to_location_id:
            raise DomainError("Source and target locations cannot be the same")
        get_stock_location(self.db, self.tenant_id, from_location_id)
        get_stock_location(self.db, self.tenant_id, to_location_id, self.target_types)


class PutawayService(TransferService):
    """After receiving, move goods from the receiving dock to bins; can be linked to the source goods receipt."""

    doc_type = DOC_PUTAWAY
    target_types = ("BIN",)
    movement_out = MOVE_PUTAWAY_OUT
    movement_in = MOVE_PUTAWAY_IN

    def validate_ref_document(self, ref_document_id: uuid.UUID | None) -> None:
        if ref_document_id is not None:
            grn = get_document(self.db, self.tenant_id, DOC_GRN, ref_document_id)
            require_status(grn, (GRN_POSTED,), "put away")


class MoveService(TransferService):
    """Internal move (Ninso MoveLocation / CombineLocation): transfer between any two stock-holding locations."""

    doc_type = DOC_MOVE
    target_types = STOCK_LOCATION_TYPES
    movement_out = MOVE_MOVE_OUT
    movement_in = MOVE_MOVE_IN
