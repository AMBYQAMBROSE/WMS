import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import false, func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError
from app.core.formatting import qty_text
from app.models.document import DocumentHeader, DocumentLine
from app.models.location import Location
from app.models.stock import StockBalance
from app.repositories.base import check_version
from app.schemas.document import DocumentSummary
from app.schemas.outbound import (
    SalesOrderIn,
    SalesOrderLineIn,
    SalesOrderLineRead,
    SalesOrderRead,
    ShortageRead,
    ShortageReportRow,
)
from app.services.document_common import (
    DOC_PICK,
    DOC_RETURN_IN,
    DOC_SHIP,
    DOC_SO,
    get_active_item,
    get_customer,
    get_document,
    get_stock_location,
    get_uom,
    list_documents,
    next_doc_no,
    require_status,
    tenant_now,
)
from app.services.stock_service import allocatable_balances, to_base_qty

SO_DRAFT = "DRAFT"
SO_CONFIRMED = "CONFIRMED"
SO_IN_PROGRESS = "IN_PROGRESS"
SO_PARTIALLY_SHIPPED = "PARTIALLY_SHIPPED"
SO_SHIPPED = "SHIPPED"
SO_CLOSED = "CLOSED"
SO_CANCELLED = "CANCELLED"
SO_FULFILLING = (SO_CONFIRMED, SO_IN_PROGRESS, SO_PARTIALLY_SHIPPED)

PICK_OPEN = "OPEN"
PICK_POSTED = "POSTED"
PICK_CANCELLED = "CANCELLED"

SHIP_DRAFT = "DRAFT"
SHIP_POSTED = "POSTED"

RETURN_DRAFT = "DRAFT"
RETURN_POSTED = "POSTED"
RETURN_CANCELLED = "CANCELLED"

ZERO = Decimal(0)


@dataclass
class LineProgress:
    """Fulfilment progress of an order line, all in base units"""

    ordered: Decimal
    allocated: Decimal = ZERO  # reserved on open pick lists
    picked: Decimal = ZERO  # picked on posted pick lists
    shipped: Decimal = ZERO  # shipped on posted shipments
    returned: Decimal = ZERO  # posted customer returns (does not affect fulfilment, only limits returnable quantity)

    @property
    def unallocated(self) -> Decimal:
        """Quantity still to allocate. Short-picked quantities come back here and can be allocated again after replenishment"""
        return max(self.ordered - self.allocated - self.picked, ZERO)

    @property
    def staged(self) -> Decimal:
        """Quantity picked to the staging area but not yet shipped"""
        return self.picked - self.shipped


class SalesOrderService:
    """Sales order (outbound order): create -> confirm -> allocate (creates a pick list and reserves stock) -> pick -> ship.
    Line qty_planned is the ordered quantity (in the order unit); qty_actual is the cumulative shipped quantity (in base units).
    """

    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self, **filters) -> list[DocumentHeader]:
        return list_documents(self.db, self.tenant_id, DOC_SO, **filters)

    def get(self, so_id: uuid.UUID, lock: bool = False) -> DocumentHeader:
        return get_document(self.db, self.tenant_id, DOC_SO, so_id, lock=lock)

    def read(self, so: DocumentHeader) -> SalesOrderRead:
        progress = self.progress(so)
        summary = DocumentSummary.model_validate(so)
        lines = []
        for line in so.lines:
            p = progress[line.id]
            lines.append(
                SalesOrderLineRead(
                    id=line.id,
                    line_no=line.line_no,
                    item=line.item,
                    uom=line.uom,
                    qty_planned=line.qty_planned,
                    ordered_base=p.ordered,
                    allocated=p.allocated,
                    picked=p.picked,
                    shipped=p.shipped,
                    unallocated=p.unallocated,
                    returned=p.returned,
                )
            )
        return SalesOrderRead(**summary.model_dump(), lines=lines)

    def create(self, data: SalesOrderIn) -> DocumentHeader:
        get_customer(self.db, self.tenant_id, data.partner_id)
        so = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_SO,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_SO),
            status=SO_DRAFT,
            partner_id=data.partner_id,
            expected_date=data.expected_date,
            remark=data.remark,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        so.lines = self._build_lines(data.lines)
        self.db.add(so)
        self.db.flush()
        return self.get(so.id)

    def update(self, so_id: uuid.UUID, data: SalesOrderIn) -> DocumentHeader:
        so = self.get(so_id, lock=True)
        check_version(so, data.row_version, f"Sales order {so.doc_no}")
        require_status(so, (SO_DRAFT,), "edit")
        get_customer(self.db, self.tenant_id, data.partner_id)
        new_lines = self._build_lines(data.lines)
        so.partner_id = data.partner_id
        so.expected_date = data.expected_date
        so.remark = data.remark
        so.lines.clear()
        self.db.flush()
        so.lines.extend(new_lines)
        self._touch(so)
        self.db.flush()
        return self.get(so.id)

    def confirm(self, so_id: uuid.UUID) -> DocumentHeader:
        so = self.get(so_id, lock=True)
        require_status(so, (SO_DRAFT,), "confirm")
        so.status = SO_CONFIRMED
        self._touch(so)
        self.db.flush()
        return so

    def allocate(
        self,
        so_id: uuid.UUID,
        staging_location_id: uuid.UUID,
        source_location_id: uuid.UUID | None = None,
    ) -> tuple[DocumentHeader, list[ShortageRead]]:
        """Reserve stock FEFO/FIFO for the unallocated quantity and create one pick list. If stock is short, allocate what is possible and return the rest as shortages.

        source_location_id (cross-docking): allocate only from this receiving dock, so freshly received goods go to staging without putaway.
        """
        so = self.get(so_id, lock=True)
        require_status(so, SO_FULFILLING, "allocate")
        staging = get_stock_location(self.db, self.tenant_id, staging_location_id, ("DOCK",))
        if source_location_id is not None:
            source = get_stock_location(self.db, self.tenant_id, source_location_id, ("DOCK",))
            if source.id == staging.id:
                raise DomainError("The cross-dock source and the staging location cannot be the same location")
        progress = self.progress(so)
        today = tenant_now(self.db, self.tenant_id).date()

        pick_lines: list[tuple[str, DocumentLine]] = []
        shortages: list[ShortageRead] = []
        for so_line in so.lines:
            need = progress[so_line.id].unallocated
            if need <= 0:
                continue
            for balance in allocatable_balances(
                self.db, self.tenant_id, so_line.item_id, today, source_location_id
            ):
                take = min(balance.qty_on_hand - balance.qty_allocated, need)
                if take <= 0:
                    continue
                balance.qty_allocated += take
                balance.updated_by = self.user_id
                balance.row_version += 1
                pick_lines.append(
                    (
                        balance.location.code,
                        DocumentLine(
                            tenant_id=self.tenant_id,
                            line_no=0,
                            item_id=so_line.item_id,
                            uom_id=so_line.item.base_uom_id,
                            qty_planned=take,
                            qty_actual=ZERO,
                            batch_no=balance.batch_no,
                            expiry_date=balance.expiry_date,
                            from_location_id=balance.location_id,
                            to_location_id=staging.id,
                            ref_line_id=so_line.id,
                            created_by=self.user_id,
                            updated_by=self.user_id,
                        ),
                    )
                )
                need -= take
                if need <= 0:
                    break
            if need > 0:
                shortages.append(
                    ShortageRead(
                        line_id=so_line.id,
                        sku_code=so_line.item.sku_code,
                        name=so_line.item.name,
                        qty=need,
                        uom_code=so_line.item.base_uom.code,
                    )
                )

        if not pick_lines:
            if not shortages:
                raise ConflictError(f"Order {so.doc_no} has nothing left to allocate")
            listed = ", ".join(f"{s.sku_code} short {qty_text(s.qty)}" for s in shortages[:5])
            raise DomainError(f"Insufficient stock, nothing could be allocated: {listed}")

        # Sorted by bin code so the picker can walk the route in order
        pick_lines.sort(key=lambda pair: (pair[0], pair[1].item_id.hex))
        for line_no, (_, line) in enumerate(pick_lines, start=1):
            line.line_no = line_no

        pick = DocumentHeader(
            tenant_id=self.tenant_id,
            doc_type=DOC_PICK,
            doc_no=next_doc_no(self.db, self.tenant_id, DOC_PICK),
            status=PICK_OPEN,
            partner_id=so.partner_id,
            ref_document_id=so.id,
            location_id=staging.id,
            remark="Cross-dock: allocated directly from the receiving dock" if source_location_id is not None else None,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        pick.lines = [line for _, line in pick_lines]
        self.db.add(pick)
        if so.status == SO_CONFIRMED:
            so.status = SO_IN_PROGRESS
        self._touch(so)
        self.db.flush()
        return pick, shortages

    def cancel(self, so_id: uuid.UUID) -> DocumentHeader:
        so = self.get(so_id, lock=True)
        require_status(so, (SO_DRAFT,) + SO_FULFILLING, "cancel")
        progress = self.progress(so).values()
        if any(p.allocated > 0 for p in progress):
            raise DomainError("The order has open pick lists; cancel them first")
        if any(p.picked > 0 or p.shipped > 0 for p in progress):
            raise DomainError("The order already has picks or shipments and cannot be cancelled; close it instead")
        so.status = SO_CANCELLED
        self._touch(so)
        self.db.flush()
        return so

    def close(self, so_id: uuid.UUID) -> DocumentHeader:
        """Stop shipping the remaining quantity (short close). Requires no open picks/shipments and everything picked already shipped"""
        so = self.get(so_id, lock=True)
        require_status(so, SO_FULFILLING, "close")
        progress = self.progress(so).values()
        if any(p.allocated > 0 for p in progress):
            raise DomainError("The order has open pick lists; finish or cancel them first")
        if self._has_draft_shipment(so.id):
            raise DomainError("The order has unposted shipments; post or cancel them first")
        if any(p.staged > 0 for p in progress):
            raise DomainError("There are picked but unshipped goods in staging; ship them first")
        so.status = SO_CLOSED
        self._touch(so)
        self.db.flush()
        return so

    def progress(self, so: DocumentHeader) -> dict[uuid.UUID, LineProgress]:
        result = {
            line.id: LineProgress(
                ordered=to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_planned),
                shipped=line.qty_actual,
            )
            for line in so.lines
        }
        rows = self.db.execute(
            select(
                DocumentLine.ref_line_id,
                DocumentHeader.status,
                func.sum(DocumentLine.qty_planned),
                func.sum(DocumentLine.qty_actual),
            )
            .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
            .where(
                DocumentHeader.tenant_id == self.tenant_id,
                DocumentHeader.ref_document_id == so.id,
                DocumentHeader.doc_type == DOC_PICK,
                DocumentHeader.is_deleted == false(),
            )
            .group_by(DocumentLine.ref_line_id, DocumentHeader.status)
        )
        for ref_line_id, status, planned, actual in rows:
            p = result.get(ref_line_id)
            if p is None:
                continue
            if status == PICK_OPEN:
                p.allocated += planned
            elif status == PICK_POSTED:
                p.picked += actual

        # Customer returns may be recorded in any unit; convert each line to base units
        returns = self.db.scalars(
            select(DocumentLine)
            .join(DocumentHeader, DocumentHeader.id == DocumentLine.document_id)
            .where(
                DocumentHeader.tenant_id == self.tenant_id,
                DocumentHeader.ref_document_id == so.id,
                DocumentHeader.doc_type == DOC_RETURN_IN,
                DocumentHeader.status == RETURN_POSTED,
                DocumentHeader.is_deleted == false(),
            )
        ).unique()
        for line in returns:
            p = result.get(line.ref_line_id)
            if p is not None:
                p.returned += to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty_actual)
        return result

    def shortage_report(self) -> list[ShortageReportRow]:
        orders = list(
            self.db.scalars(
                select(DocumentHeader)
                .where(
                    DocumentHeader.tenant_id == self.tenant_id,
                    DocumentHeader.doc_type == DOC_SO,
                    DocumentHeader.status.in_(SO_FULFILLING),
                    DocumentHeader.is_deleted == false(),
                )
                .order_by(DocumentHeader.expected_date, DocumentHeader.created_at)
            ).unique()
        )
        available_cache: dict[uuid.UUID, Decimal] = {}
        rows = []
        for so in orders:
            progress = self.progress(so)
            for line in so.lines:
                p = progress[line.id]
                if p.unallocated <= 0:
                    continue
                if line.item_id not in available_cache:
                    available_cache[line.item_id] = self._available(line.item_id)
                rows.append(
                    ShortageReportRow(
                        so_id=so.id,
                        so_doc_no=so.doc_no,
                        customer=so.partner.name if so.partner else "",
                        expected_date=so.expected_date,
                        line_id=line.id,
                        item=line.item,
                        ordered=p.ordered,
                        unallocated=p.unallocated,
                        available=available_cache[line.item_id],
                    )
                )
        return rows

    def _available(self, item_id: uuid.UUID) -> Decimal:
        total = self.db.scalar(
            select(func.sum(StockBalance.qty_on_hand - StockBalance.qty_allocated))
            .join(Location, Location.id == StockBalance.location_id)
            .where(
                StockBalance.tenant_id == self.tenant_id,
                StockBalance.item_id == item_id,
                Location.location_type == "BIN",
            )
        )
        return total or ZERO

    def _has_draft_shipment(self, so_id: uuid.UUID) -> bool:
        return (
            self.db.scalar(
                select(func.count())
                .select_from(DocumentHeader)
                .where(
                    DocumentHeader.tenant_id == self.tenant_id,
                    DocumentHeader.doc_type == DOC_SHIP,
                    DocumentHeader.ref_document_id == so_id,
                    DocumentHeader.status == SHIP_DRAFT,
                    DocumentHeader.is_deleted == false(),
                )
            )
            or 0
        ) > 0

    def _build_lines(self, lines_in: list[SalesOrderLineIn]) -> list[DocumentLine]:
        lines = []
        for line_no, line in enumerate(lines_in, start=1):
            item = get_active_item(self.db, self.tenant_id, line.item_id)
            get_uom(self.db, self.tenant_id, line.uom_id)
            to_base_qty(self.db, self.tenant_id, item, line.uom_id, line.qty)
            lines.append(
                DocumentLine(
                    tenant_id=self.tenant_id,
                    line_no=line_no,
                    item_id=item.id,
                    uom_id=line.uom_id,
                    qty_planned=line.qty,
                    qty_actual=ZERO,
                    created_by=self.user_id,
                    updated_by=self.user_id,
                )
            )
        return lines

    def _touch(self, so: DocumentHeader) -> None:
        so.updated_by = self.user_id
        so.row_version += 1
