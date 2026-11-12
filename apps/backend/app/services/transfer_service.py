import uuid
from decimal import Decimal

from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.formatting import qty_text
from app.models.document import DocumentHeader, DocumentLine
from app.models.location import STOCK_LOCATION_TYPES, Location
from app.models.stock import StockBalance
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
# Putaway sheet made from a posted receipt: lines are put away one by one (put), then the sheet is posted
PUTAWAY_OPEN = "TO_PUT_AWAY"


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
        require_status(document, (TRANSFER_DRAFT, PUTAWAY_OPEN), "post")
        if document.status == PUTAWAY_OPEN:
            open_lines = [line for line in document.lines if line.confirmed_at is None]
            if open_lines:
                left = ", ".join(f"{line.item.sku_code} {qty_text(line.qty_planned)} {line.uom.code}" for line in open_lines[:5])
                raise DomainError(f"Not everything is put away yet: {left}")

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
        require_status(document, (TRANSFER_DRAFT, PUTAWAY_OPEN), "cancel")
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
            self._replace_sheet(grn.id)

    def _replace_sheet(self, grn_id: uuid.UUID) -> None:
        """A putaway planned by hand for a receipt replaces its putaway sheet, so the same dock stock is not on two
        documents. A sheet already being worked is not thrown away: finish or cancel it first."""
        for summary in self.list(ref_document_id=grn_id, status=PUTAWAY_OPEN):
            sheet = self.get(summary.id, lock=True)
            if any(line.confirmed_at for line in sheet.lines):
                raise DomainError(f"Putaway sheet {sheet.doc_no} for this receipt is in progress; finish or cancel it first")
            sheet.status = TRANSFER_CANCELLED
            sheet.remark = "Replaced by a putaway created by hand"
            sheet.updated_by = self.user_id
            sheet.row_version += 1
            self.db.flush()

    def create_sheet(self, grn: DocumentHeader) -> DocumentHeader | None:
        """Putaway sheet for a receipt just posted into a dock: one line per received line, each with a suggested bin.
        Nothing is created for goods received straight into a bin."""
        if grn.location is None or grn.location.location_type != "DOCK" or not grn.lines:
            return None
        lines = [
            DocumentLine(
                tenant_id=self.tenant_id,
                line_no=line_no,
                item_id=grn_line.item_id,
                uom_id=grn_line.uom_id,
                qty_planned=grn_line.qty_actual,
                qty_actual=Decimal(0),
                batch_no=grn_line.batch_no,
                expiry_date=grn_line.expiry_date,
                from_location_id=grn.location_id,
                to_location_id=self._suggest_bin(grn_line.item_id, grn_line.batch_no),
                ref_line_id=grn_line.id,
                created_by=self.user_id,
                updated_by=self.user_id,
            )
            for line_no, grn_line in enumerate(grn.lines, start=1)
        ]
        sheet = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=self.doc_type,
            doc_no=next_doc_no(self.db, self.tenant_id, self.doc_type),
            status=PUTAWAY_OPEN,
            ref_document_id=grn.id,
            location_id=grn.location_id,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        sheet.lines = lines
        self.db.add(sheet)
        self.db.flush()
        return sheet

    def _suggest_bin(self, item_id: uuid.UUID, batch_no: str | None) -> uuid.UUID | None:
        """The usable bin already holding most of this item (a bin with the same batch first), so an item's stock stays
        together. None when the item is in no bin yet: the operator chooses a bin and scans it."""
        rows = self.db.execute(
            select(StockBalance.location_id, StockBalance.batch_no, StockBalance.qty_on_hand)
            .join(Location, Location.id == StockBalance.location_id)
            .where(
                StockBalance.tenant_id == self.tenant_id,
                StockBalance.item_id == item_id,
                StockBalance.qty_on_hand > 0,
                Location.location_type == "BIN",
                Location.is_active == true(),
                Location.is_locked == false(),
                Location.is_deleted == false(),
            )
        ).all()
        totals: dict[uuid.UUID, tuple[bool, Decimal]] = {}
        for location_id, row_batch, qty in rows:
            same_batch, total = totals.get(location_id, (False, Decimal(0)))
            totals[location_id] = (same_batch or (batch_no is not None and row_batch == batch_no), total + qty)
        return max(totals.items(), key=lambda kv: kv[1])[0] if totals else None

    def put(self, document_id: uuid.UUID, line_id: uuid.UUID, to_location_id: uuid.UUID, qty: Decimal) -> DocumentHeader:
        """Record that qty of a sheet line went into a bin (any bin: the suggestion is only a suggestion).
        Less than the line's quantity splits it: the rest becomes a new open line, for another bin. A put against a
        line already done goes to the open rest split from it, so a PDA working offline can keep putting against the
        line it knows."""
        sheet = self.get(document_id, lock=True)
        require_status(sheet, (PUTAWAY_OPEN,), "put away")
        line = next((candidate for candidate in sheet.lines if candidate.id == line_id), None)
        if line is None:
            raise DomainError("Putaway line not found")
        while line is not None and line.confirmed_at is not None:
            done = line
            line = next((rest for rest in sheet.lines if rest.ref_line_id == done.id), None)
        if line is None:
            raise DomainError("This line is already fully put away")
        if qty > line.qty_planned:
            raise DomainError(
                f"{line.item.sku_code}: only {qty_text(line.qty_planned)} {line.uom.code} left to put away, got {qty_text(qty)}"
            )
        self._validate_locations(line.from_location_id, to_location_id)
        if qty < line.qty_planned:
            sheet.lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=max(existing.line_no for existing in sheet.lines) + 1,
                    item_id=line.item_id,
                    uom_id=line.uom_id,
                    qty_planned=line.qty_planned - qty,
                    qty_actual=Decimal(0),
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    from_location_id=line.from_location_id,
                    to_location_id=line.to_location_id,
                    ref_line_id=line.id,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
            line.qty_planned = qty
        line.qty_actual = qty
        line.to_location_id = to_location_id
        line.confirmed_at = utcnow()
        line.confirmed_by = self.user_id
        line.updated_by = self.user_id
        sheet.updated_by = self.user_id
        sheet.row_version += 1
        self.db.flush()
        # Only the foreign keys changed; reload the relationships the response shows
        self.db.expire(line, ["to_location", "confirmer"])
        return self.get(sheet.id)


class MoveService(TransferService):
    """Internal move (Ninso MoveLocation / CombineLocation): transfer between any two stock-holding locations."""

    doc_type = DOC_MOVE
    target_types = STOCK_LOCATION_TYPES
    movement_out = MOVE_MOVE_OUT
    movement_in = MOVE_MOVE_IN
