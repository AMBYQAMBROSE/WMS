import uuid
from collections import defaultdict
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.core.formatting import qty_text
from app.models.document import DocumentHeader, DocumentLine
from app.models.item import Item
from app.models.location import STOCK_LOCATION_TYPES, Location
from app.models.stock import StockBalance
from app.schemas.document import TransferIn
from app.services.document_common import (
    DOC_GRN,
    DOC_MOVE,
    DOC_PUTAWAY,
    DOC_RECALL,
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
from app.services.item_service import pallet_qty
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
OPEN_STATUSES = (TRANSFER_DRAFT, PUTAWAY_OPEN)


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
        document = self.get(document.id)
        self.check_one_pallet_per_bin(document)
        return document

    def post(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, OPEN_STATUSES, "post")
        if document.status == PUTAWAY_OPEN:
            open_lines = [line for line in document.lines if line.confirmed_at is None]
            if open_lines:
                left = ", ".join(f"{line.item.sku_code} {qty_text(line.qty_planned)} {line.uom.code}" for line in open_lines[:5])
                raise DomainError(f"Not everything is put away yet: {left}")
        self.check_one_pallet_per_bin(document)

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
        require_status(document, OPEN_STATUSES, "cancel")
        document.status = TRANSFER_CANCELLED
        document.updated_by = self.user_id
        document.row_version += 1
        self.db.flush()
        return document

    def check_one_pallet_per_bin(self, document: DocumentHeader, only_bin: uuid.UUID | None = None) -> None:
        """A bin holds one pallet: a single item, at most its pallet quantity. Checked for every bin this document
        brings stock into (or only `only_bin`), counting what is there, what other open putaways and moves bring
        (their planned quantities: a putaway sheet's suggested bin is reserved for it) and this document's own lines.
        Docks have no limit. The bins are row-locked first, so two documents for one bin are checked one after the
        other and the second sees the first."""
        change: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = defaultdict(Decimal)
        items = {}
        for line in document.lines:
            items[line.item_id] = line.item
            qty = to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_planned)
            if line.to_location_id is not None:
                change[(line.to_location_id, line.item_id)] += qty
            change[(line.from_location_id, line.item_id)] -= qty
        targets = sorted(
            {bin_id for (bin_id, _), qty in change.items() if qty > 0 and only_bin in (None, bin_id)}, key=str
        )
        if not targets:
            return
        bins = {
            location.id: location
            for location in self.db.scalars(
                select(Location)
                .where(Location.id.in_(targets), Location.location_type == "BIN")
                .with_hint(Location, "WITH (UPDLOCK, ROWLOCK)", "mssql")
            )
        }
        if not bins:
            return

        totals: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = defaultdict(Decimal)
        for location_id, item_id, qty in self.db.execute(
            select(StockBalance.location_id, StockBalance.item_id, StockBalance.qty_on_hand).where(
                StockBalance.tenant_id == self.tenant_id,
                StockBalance.location_id.in_(bins),
                StockBalance.qty_on_hand != 0,
            )
        ):
            totals[(location_id, item_id)] += qty
        others = (
            select(DocumentLine)
            .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
            .where(
                DocumentHeader.tenant_id == self.tenant_id,
                DocumentHeader.doc_type.in_((DOC_PUTAWAY, DOC_MOVE)),
                DocumentHeader.status.in_(OPEN_STATUSES),
                DocumentLine.to_location_id.in_(bins),
            )
        )
        if document.id is not None:
            others = others.where(DocumentHeader.id != document.id)
        for line in self.db.scalars(others):
            items[line.item_id] = line.item
            totals[(line.to_location_id, line.item_id)] += to_base_qty(
                self.db, self.tenant_id, line.item, line.uom_id, line.qty_planned
            )
        for key, qty in change.items():
            if key[0] in bins:
                totals[key] += qty

        for bin_id, location in bins.items():
            held = {item_id: qty for (b, item_id), qty in totals.items() if b == bin_id and qty > 0}
            if len(held) > 1:
                skus = ", ".join(sorted(self._item(items, item_id).sku_code for item_id in held))
                raise DomainError(f"Bin {location.code} holds one pallet of one item; this would put {skus} together there")
            for item_id, qty in held.items():
                item = self._item(items, item_id)
                limit = pallet_qty(item)
                if qty > limit:
                    unit = item.base_uom.code
                    raise DomainError(
                        f"Bin {location.code} holds one pallet: {qty_text(qty)} {unit} of {item.sku_code} is more than "
                        f"one pallet ({qty_text(limit)} {unit}); put the rest in another bin"
                    )

    def _item(self, known: dict[uuid.UUID, Item], item_id: uuid.UUID) -> Item:
        """An item by id, from those already loaded (stock in a bin may be of an item no line here names)"""
        if item_id not in known:
            known[item_id] = self.db.get(Item, item_id)
        return known[item_id]

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
        """Putaway sheet for a receipt just posted into a dock. A bin holds one pallet, so each received line is cut
        into pallets (see _pallet_size: 1200 EA at 500 a pallet -> 500, 500, 200) and every pallet gets its own empty
        bin in the dock's warehouse. What finds no free bin stays as one line without a bin, for the operator to place
        (split by putting part of it at a time). Nothing is created for goods received straight into a bin."""
        if grn.location is None or grn.location.location_type != "DOCK" or not grn.lines:
            return None
        sizes = [(grn_line, self._pallet_size(grn_line)) for grn_line in grn.lines]
        needed = sum(int((grn_line.qty_actual / size).to_integral_value(rounding=ROUND_CEILING)) for grn_line, size in sizes)
        free_bins = iter(self._claim_bins(grn.location, needed))
        lines: list[DocumentLine] = []
        for grn_line, size in sizes:
            left = grn_line.qty_actual
            while left > 0:
                bin_id = next(free_bins, None)
                qty = min(size, left) if bin_id is not None else left
                lines.append(
                    DocumentLine(
                        tenant_id=self.tenant_id,
                        line_no=len(lines) + 1,
                        item_id=grn_line.item_id,
                        uom_id=grn_line.uom_id,
                        qty_planned=qty,
                        qty_actual=Decimal(0),
                        batch_no=grn_line.batch_no,
                        expiry_date=grn_line.expiry_date,
                        from_location_id=grn.location_id,
                        to_location_id=bin_id,
                        ref_line_id=grn_line.id,
                        created_by=self.user_id,
                        updated_by=self.user_id,
                    )
                )
                left -= qty
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

    def remaining_for_receipt(self, grn_id: uuid.UUID) -> dict[uuid.UUID, Decimal]:
        """What is left to put away of each line of a posted receipt, in the line's unit: its received quantity less
        what putaways made for this receipt already cover (posted or drafted by hand, or done on its putaway sheet).
        Used to prefill a putaway planned by hand, so a receipt that is already put away offers nothing again."""
        grn = get_document(self.db, self.tenant_id, DOC_GRN, grn_id)

        def base(line: DocumentLine, qty: Decimal) -> Decimal:
            return to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, qty)

        covered: dict[tuple, Decimal] = {}
        for summary in self.list(ref_document_id=grn.id, limit=200):
            if summary.status == TRANSFER_CANCELLED:
                continue
            for line in summary.lines:
                # An open sheet line is replaced by the putaway planned by hand; only what is done on it counts
                if summary.status == PUTAWAY_OPEN and line.confirmed_at is None:
                    continue
                key = (line.item_id, line.batch_no, line.expiry_date)
                covered[key] = covered.get(key, Decimal(0)) + base(line, line.qty_actual)

        remaining: dict[uuid.UUID, Decimal] = {}
        for line in grn.lines:
            key = (line.item_id, line.batch_no, line.expiry_date)
            received = base(line, line.qty_actual)
            done = min(covered.get(key, Decimal(0)), received)
            covered[key] = covered.get(key, Decimal(0)) - done
            remaining[line.id] = ((received - done) / base(line, Decimal(1))).quantize(Decimal("0.0001"))
        return remaining

    def _pallet_size(self, line: DocumentLine) -> Decimal:
        """One pallet in the line's unit: the item's pallet quantity (pallet_qty) rounded down to whole units of the
        line. A unit as large as a pallet or larger is one pallet per unit."""
        unit_base = to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, Decimal(1))
        return max(Decimal(1), (pallet_qty(line.item) / unit_base).to_integral_value(rounding=ROUND_FLOOR))

    def _claim_bins(self, dock: Location, count: int) -> list[uuid.UUID]:
        """Up to `count` usable bins in the dock's warehouse that hold nothing and are not the target of an open
        putaway or move (a pallet on its way there), in location order, each row-locked until this transaction ends.

        Receipts posted at the same time must not get the same bin. Free bins are found by a plain read, then locked
        by primary key (only those rows) with UPDLOCK + READPAST: a bin another receipt is still claiming is skipped,
        not waited for (no blocking, no deadlock). A locked bin is checked again: the first read may not yet have
        seen a receipt that committed its claim meanwhile, and a statement started after the lock does."""
        if count <= 0:
            return []
        warehouse_path = "/" + dock.path.strip("/").split("/")[0] + "/"
        occupied = select(StockBalance.location_id).where(
            StockBalance.tenant_id == self.tenant_id, StockBalance.qty_on_hand > 0
        )
        incoming = (
            select(DocumentLine.to_location_id)
            .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
            .where(
                DocumentHeader.tenant_id == self.tenant_id,
                DocumentHeader.doc_type.in_((DOC_PUTAWAY, DOC_MOVE)),
                DocumentHeader.status.in_((TRANSFER_DRAFT, PUTAWAY_OPEN)),
                DocumentLine.to_location_id.is_not(None),
            )
        )

        def free(*extra):
            return select(Location.id).where(
                Location.tenant_id == self.tenant_id,
                Location.location_type == "BIN",
                Location.path.startswith(warehouse_path, autoescape=True),
                Location.is_active == true(),
                Location.is_locked == false(),
                Location.is_deleted == false(),
                Location.id.not_in(occupied),
                Location.id.not_in(incoming),
                *extra,
            )

        claimed: list[uuid.UUID] = []
        tried: list[uuid.UUID] = []
        while len(claimed) < count:
            candidates = list(
                self.db.scalars(
                    free(Location.id.not_in(tried) if tried else true())
                    .order_by(Location.path)
                    .limit(count - len(claimed))
                )
            )
            if not candidates:
                break
            tried += candidates
            locked = set(
                self.db.scalars(
                    select(Location.id)
                    .where(Location.id.in_(candidates))
                    .with_hint(Location, "WITH (UPDLOCK, READPAST, ROWLOCK)", "mssql")
                )
            )
            still_free = set(self.db.scalars(free(Location.id.in_(locked)))) if locked else set()
            claimed += [bin_id for bin_id in candidates if bin_id in still_free]
        return claimed

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
        self.db.expire(line, ["to_location", "confirmer", "item"])
        self.check_one_pallet_per_bin(sheet, only_bin=to_location_id)
        return self.get(sheet.id)


class MoveService(TransferService):
    """Internal move (Ninso MoveLocation / CombineLocation): transfer between any two stock-holding locations."""

    doc_type = DOC_MOVE
    target_types = STOCK_LOCATION_TYPES
    movement_out = MOVE_MOVE_OUT
    movement_in = MOVE_MOVE_IN

    def validate_ref_document(self, ref_document_id: uuid.UUID | None) -> None:
        """A move may come from a recall (moving the recalled batch to quarantine); nothing else"""
        if ref_document_id is None:
            return
        source = self.db.get(DocumentHeader, ref_document_id)
        if source is None or source.tenant_id != self.tenant_id or source.doc_type != DOC_RECALL:
            raise DomainError("A move can only be made from a recall")

    def check_one_pallet_per_bin(self, document: DocumentHeader, only_bin: uuid.UUID | None = None) -> None:
        """A recall's move gathers the recalled batch from every bin into quarantine: a holding area, not a pallet bin"""
        if document.ref_document_id is None:
            super().check_one_pallet_per_bin(document, only_bin)
