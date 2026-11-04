import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.document import CountEntry, DocumentHeader, DocumentLine, DocumentLocation
from app.models.location import STOCK_LOCATION_TYPES, Location
from app.schemas.document import CountEntryIn, CycleCountCreate
from app.services.document_common import (
    COUNT_IN_PROGRESS,
    DOC_COUNT,
    LOCK_RANGE,
    active_count_for_location,
    get_active_item,
    get_document,
    get_uom,
    list_documents,
    next_doc_no,
    normalize_tracking,
    require_status,
    utcnow,
)
from app.services.stock_service import (
    MOVE_COUNT_GAIN,
    MOVE_COUNT_LOSS,
    Movement,
    apply_movements,
    balances_at_locations,
    locked_balance_qty,
    stock_key,
    to_base_qty,
)

COUNT_POSTED = "POSTED"
COUNT_CANCELLED = "CANCELLED"

MAX_LISTED = 5


def _line_key(line: DocumentLine) -> tuple:
    return stock_key(line.item_id, line.to_location_id, line.batch_no, line.expiry_date)


class CycleCountService:
    """Cycle count:
    Counting starts on creation (COUNTING); covered locations are frozen and lines are created from current stock (book quantity snapshot).
    Enter counts (several people, PDA offline resubmits) -> request a recount if needed (new round) -> post to write count gain/loss and unfreeze.
    A line's to_location is the counted location; quantities are always base units.
    """

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_COUNT, **filters)

    def get(self, document_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_COUNT, document_id, lock=lock)

    def create(self, data: CycleCountCreate) -> DocumentHeader:
        location_ids = list(dict.fromkeys(data.location_ids))
        # Lock these location rows: if two counts cover the same location, the second waits for the first to commit, then is rejected
        locations = list(
            self.db.scalars(
                select(Location)
                .with_hint(Location, LOCK_RANGE, "mssql")
                .where(Location.tenant_id == self.tenant_id, Location.id.in_(location_ids))
                .execution_options(populate_existing=True)
            )
        )
        found = {location.id: location for location in locations}
        for location_id in location_ids:
            location = found.get(location_id)
            if location is None or location.is_deleted:
                raise DomainError("Location not found")
            if not location.is_active:
                raise DomainError(f"Location {location.code} is inactive")
            if location.location_type not in STOCK_LOCATION_TYPES:
                raise DomainError(f"Location {location.code} does not hold stock and does not need counting")
            # Locked locations can still be counted (they are often locked for exactly that), but not in two counts at once
            other = active_count_for_location(self.db, self.tenant_id, location_id)
            if other is not None:
                raise DomainError(f"Location {location.code} is already in cycle count {other.doc_no}")

        current = balances_at_locations(self.db, self.tenant_id, location_ids)
        reserved = [b for b in current if b.qty_allocated > 0]
        if reserved:
            # Stock reserved by pick lists would block: a count loss cannot post below the reservation, and the pick cannot post on a frozen location
            listed = ", ".join(f"{b.location.code} {b.item.sku_code}" for b in reserved[:MAX_LISTED])
            raise DomainError(f"This stock is reserved by pick lists; finish or cancel the picks before counting: {listed}")

        document = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_COUNT,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_COUNT),
            status=COUNT_IN_PROGRESS,
            remark=data.remark,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        document.count_locations = [
            DocumentLocation(
                tenant_id=self.tenant_id,
                location_id=location_id,
                created_by=self.user_id,
                updated_by=self.user_id,
            )
            for location_id in location_ids
        ]
        balances = sorted(
            current,
            key=lambda b: (b.location.code, b.item.sku_code, b.batch_no or "", str(b.expiry_date or "")),
        )
        document.lines = [
            DocumentLine(
                tenant_id=self.tenant_id,
                line_no=line_no,
                item_id=balance.item_id,
                uom_id=balance.item.base_uom_id,
                qty_planned=balance.qty_on_hand,
                qty_actual=0,
                batch_no=balance.batch_no,
                expiry_date=balance.expiry_date,
                to_location_id=balance.location_id,
                created_by=self.user_id,
                updated_by=self.user_id,
            )
            for line_no, balance in enumerate(balances, start=1)
        ]
        self.db.add(document)
        self.db.flush()
        return self.get(document.id)

    def record(self, document_id: uuid.UUID, entry: CountEntryIn) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (COUNT_IN_PROGRESS,), "enter counts")
        if entry.location_id not in {cl.location_id for cl in document.count_locations}:
            raise DomainError("This location is not covered by the cycle count")

        item = get_active_item(self.db, self.tenant_id, entry.item_id)
        uom_id = entry.uom_id or item.base_uom_id
        get_uom(self.db, self.tenant_id, uom_id)
        qty = to_base_qty(self.db, self.tenant_id, item, uom_id, entry.qty)
        batch_no, expiry_date = normalize_tracking(item, entry.batch_no, entry.expiry_date)

        key = stock_key(item.id, entry.location_id, batch_no, expiry_date)
        line = next((l for l in document.lines if _line_key(l) == key), None)
        if line is None:
            # Not on the books but found physically (count gain): add a line with book quantity 0
            line = DocumentLine(
                tenant_id=self.tenant_id,
                line_no=max((l.line_no for l in document.lines), default=0) + 1,
                item_id=item.id,
                uom_id=item.base_uom_id,
                qty_planned=0,
                qty_actual=0,
                batch_no=batch_no,
                expiry_date=expiry_date,
                to_location_id=entry.location_id,
                created_by=self.user_id,
                updated_by=self.user_id,
            )
            document.lines.append(line)

        now = utcnow()
        if line.confirmed_at is None or not line.count_entries:
            # A new round (first count, or after a recount was requested)
            line.count_entries.append(
                CountEntry(
                    tenant_id=self.tenant_id,
                    round=len(line.count_entries) + 1,
                    qty=qty,
                    counted_by=self.user_id,
                    counted_at=now,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
        else:
            # Resubmitted within the same round (correction or PDA resend): overwrite this round, same result as submitting once
            current = line.count_entries[-1]
            current.qty = qty
            current.counted_by = self.user_id
            current.counted_at = now
            current.updated_by = self.user_id
        line.qty_actual = qty
        line.confirmed_at = now
        line.confirmed_by = self.user_id
        line.updated_by = self.user_id
        self._touch(document)
        self.db.flush()
        # When someone else overwrites the round only the counted_by key changes; reload the counter relationship or the old counter is returned
        self.db.expire(line.count_entries[-1], ["counter"])
        self.db.expire(line, ["confirmer"])
        return self.get(document.id)

    def recount(self, document_id: uuid.UUID, line_ids: list[uuid.UUID]) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (COUNT_IN_PROGRESS,), "request a recount")
        lines = {line.id: line for line in document.lines}
        for line_id in line_ids:
            line = lines.get(line_id)
            if line is None:
                raise DomainError("Cycle count line not found")
            if line.confirmed_at is None:
                raise DomainError(f"Line {line.line_no} has not been counted in this round; no recount needed")
            line.confirmed_at = None
            line.confirmed_by = None
            line.updated_by = self.user_id
        self._touch(document)
        self.db.flush()
        return self.get(document.id)

    def post(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (COUNT_IN_PROGRESS,), "post")

        pending = [line for line in document.lines if line.confirmed_at is None]
        if pending:
            listed = ", ".join(
                f"{l.to_location.code} {l.item.sku_code}" for l in pending[:MAX_LISTED]
            )
            more = f" and {len(pending)} lines in total" if len(pending) > MAX_LISTED else ""
            raise DomainError(f"Lines not counted yet: {listed}{more}")

        # Stock that appeared on the books during the count but is not in the document (e.g. a concurrent receipt at creation) must be counted, or it would be silently skipped
        counted_keys = {_line_key(line) for line in document.lines}
        location_ids = [cl.location_id for cl in document.count_locations]
        uncovered = [
            b
            for b in balances_at_locations(self.db, self.tenant_id, location_ids)
            if stock_key(b.item_id, b.location_id, b.batch_no, b.expiry_date) not in counted_keys
        ]
        if uncovered:
            listed = ", ".join(f"{b.location.code} {b.item.sku_code}" for b in uncovered[:MAX_LISTED])
            raise DomainError(f"This stock is on the books but was not counted; enter it (enter 0 if nothing is there): {listed}")

        movements = []
        for line in sorted(document.lines, key=_line_key):
            # The difference is against the book quantity at posting time, not the snapshot at creation
            current = locked_balance_qty(
                self.db, self.tenant_id, line.item_id, line.to_location_id, line.batch_no, line.expiry_date
            )
            delta = line.qty_actual - current
            if delta == 0:
                continue
            movements.append(
                Movement(
                    item_id=line.item_id,
                    location_id=line.to_location_id,
                    batch_no=line.batch_no,
                    expiry_date=line.expiry_date,
                    qty_change=delta,
                    movement_type=MOVE_COUNT_GAIN if delta > 0 else MOVE_COUNT_LOSS,
                    ref_line_id=line.id,
                )
            )
        apply_movements(self.db, self.tenant_id, movements, self.user_id)

        document.status = COUNT_POSTED
        document.posted_at = utcnow()
        self._touch(document)
        self.db.flush()
        return document

    def cancel(self, document_id: uuid.UUID) -> DocumentHeader:
        document = self.get(document_id, lock=True)
        require_status(document, (COUNT_IN_PROGRESS,), "cancel")
        document.status = COUNT_CANCELLED
        self._touch(document)
        self.db.flush()
        return document

    def _touch(self, document: DocumentHeader) -> None:
        document.updated_by = self.user_id
        document.row_version += 1
