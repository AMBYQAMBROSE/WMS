"""The printed report of each document type: which details, which line columns, which signatures.

Built on demand from the document as it is now, never stored: a posted document does not change, so a reprint is the
same as the first print. Every print is recorded in the document's history (audit log, action PRINT).
"""

import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.core.formatting import qty_text
from app.models.audit import ACTION_PRINT, record_change
from app.models.document import DocumentHeader, DocumentLine
from app.models.tenant import Tenant
from app.models.user import User
from app.services.attachment_service import DOCUMENT_PERMISSIONS
from app.services.printing.report import BarcodeCell, Cell, Column, Report, render
from app.services.sales_order_service import SalesOrderService

if TYPE_CHECKING:  # the API layer's type only
    from app.api.deps import CurrentUser

TITLES = {
    "PO": "Purchase Order",
    "GRN": "Goods Receipt Note",
    "PUTAWAY": "Putaway",
    "MOVE": "Stock Move",
    "ADJUST": "Stock Adjustment",
    "COUNT": "Cycle Count Sheet",
    "SO": "Sales Order",
    "PICK": "Pick List",
    "SHIP": "Delivery Order",
    "RETURN_IN": "Customer Return",
    "RETURN_OUT": "Return to Supplier",
    "REPACK": "Repack",
}

STATUS = {
    "DRAFT": "Draft", "CONFIRMED": "Confirmed", "PARTIALLY_RECEIVED": "Partially received", "RECEIVED": "Received",
    "CLOSED": "Closed", "CANCELLED": "Cancelled", "POSTED": "Posted", "REVERSED": "Returned to stock", "COUNTING": "Counting", "IN_PROGRESS": "In progress",
    "PARTIALLY_SHIPPED": "Partially shipped", "SHIPPED": "Shipped", "OPEN": "To pick", "TO_PUT_AWAY": "To put away",
}

SIGNATURES = {
    "PO": ["Prepared by", "Approved by"],
    "GRN": ["Delivered by (supplier)", "Received by", "Checked by"],
    "PUTAWAY": ["Put away by", "Checked by"],
    "MOVE": ["Moved by", "Checked by"],
    "ADJUST": ["Prepared by", "Approved by"],
    "COUNT": ["Counted by", "Checked by", "Approved by"],
    "SO": ["Prepared by", "Approved by"],
    "PICK": ["Picked by", "Checked by"],
    "SHIP": ["Released by (warehouse)", "Driver", "Received by (customer)"],
    "RETURN_IN": ["Returned by (customer)", "Received by", "Checked by"],
    "RETURN_OUT": ["Released by (warehouse)", "Collected by (supplier)"],
    "REPACK": ["Repacked by", "Checked by"],
}

PARTNER_LABEL = {"PO": "Supplier", "GRN": "Supplier", "RETURN_OUT": "Supplier", "SO": "Customer", "SHIP": "Customer", "RETURN_IN": "Customer", "PICK": "Customer"}
REF_LABEL = {"GRN": "Purchase order", "PUTAWAY": "Goods receipt", "PICK": "Sales order", "SHIP": "Sales order", "RETURN_IN": "Sales order", "RETURN_OUT": "Purchase order"}
LOCATION_LABEL = {"GRN": "Received at", "PICK": "Stage at", "SO": "Staging location", "PUTAWAY": "Take from"}
DATE_LABEL = {"PO": "Expected date", "SO": "Requested date"}

LineValue = Callable[[DocumentLine], Cell]


def _location(loc) -> str:
    return loc.code if loc else ""


def _date(value: date | None) -> str:
    return value.isoformat() if value else ""


def _item_barcode(line: DocumentLine) -> BarcodeCell:
    """The item's barcode (or SKU when it has none, as on its label) with SKU and name under it"""
    return BarcodeCell(line.item.barcode or line.item.sku_code, f"{line.item.sku_code} {line.item.name}")


def _bin_barcode(loc) -> Cell:
    return BarcodeCell(loc.code, loc.code) if loc else ""


def is_putaway_sheet(doc: DocumentHeader) -> bool:
    """A putaway made from a receipt and worked line by line (as opposed to a free putaway entered in one go)"""
    return doc.doc_type == "PUTAWAY" and (doc.status == "TO_PUT_AWAY" or any(line.confirmed_at for line in doc.lines))


class DocumentReportService:
    def __init__(self, db: Session, user: "CurrentUser"):
        self.db = db
        self.user = user
        tenant = db.get(Tenant, user.tenant_id)
        self.tenant_name = tenant.name if tenant else ""
        self.tz = ZoneInfo(tenant.default_timezone if tenant else "UTC")

    def pdf(self, document_id: uuid.UUID) -> tuple[bytes, str]:
        doc = self._document(document_id)
        report = self.build(doc)
        record_change(
            self.db, tenant_id=doc.tenant_id, entity_type="document", entity_id=doc.id,
            entity_label=f"{doc.doc_type} {doc.doc_no}", changes={"printed": [None, report.title]}, action=ACTION_PRINT,
        )
        return render(report), f"{doc.doc_no}.pdf"

    def _document(self, document_id: uuid.UUID) -> DocumentHeader:
        doc = self.db.get(DocumentHeader, document_id)
        module = DOCUMENT_PERMISSIONS.get(doc.doc_type, (None, None))[0] if doc else None
        # Without read access the document does not exist for this user, as everywhere else
        if doc is None or doc.tenant_id != self.user.tenant_id or doc.is_deleted or f"{module}.read" not in self.user.permissions:
            raise NotFoundError("Document not found")
        return doc

    def _time(self, value: datetime | None) -> str:
        # Stored as naive UTC; printed in the warehouse's own time zone
        if value is None:
            return ""
        return value.replace(tzinfo=ZoneInfo("UTC")).astimezone(self.tz).strftime("%Y-%m-%d %H:%M")

    def _user(self, user_id: uuid.UUID | None) -> str:
        user = self.db.get(User, user_id) if user_id else None
        return user.display_name if user else ""

    # ----- building the report -----

    def build(self, doc: DocumentHeader) -> Report:
        t = doc.doc_type
        columns, rows, totals = self._lines(doc)
        printed_at = datetime.now(self.tz).strftime("%Y-%m-%d %H:%M")
        return Report(
            title="Putaway Sheet" if is_putaway_sheet(doc) else TITLES.get(t, t),
            doc_no=doc.doc_no,
            status=STATUS.get(doc.status, doc.status),
            company=self.tenant_name,
            printed=f"Printed {printed_at} by {self.user.display_name or self.user.username}",
            info=self._info(doc),
            columns=columns,
            rows=rows,
            totals=totals,
            remark=doc.remark or "",
            signatures=SIGNATURES.get(t, []),
            declaration="Received the goods listed above in good order and condition." if t == "SHIP" else "",
            watermark="CANCELLED" if doc.status == "CANCELLED" else ("DRAFT" if doc.status == "DRAFT" and t in ("PO", "SO", "SHIP") else ""),
        )

    def _info(self, doc: DocumentHeader) -> list[tuple[str, str]]:
        t = doc.doc_type
        info: list[tuple[str, str]] = []
        if doc.partner:
            p = doc.partner
            info.append((PARTNER_LABEL.get(t, "Partner"), f"{p.name} ({p.code})"))
            if t in ("SHIP", "SO", "RETURN_OUT", "PO"):
                info.append(("Address", p.address or ""))
                contact = " · ".join(x for x in (p.contact_name, p.contact_phone) if x)
                info.append(("Contact", contact))
        if doc.ref_document:
            info.append((REF_LABEL.get(t, "Source document"), doc.ref_document.doc_no))
        if doc.location:
            info.append((LOCATION_LABEL.get(t, "Location"), f"{doc.location.code} {doc.location.name}"))
        if doc.expected_date:
            info.append((DATE_LABEL.get(t, "Date"), _date(doc.expected_date)))
        if doc.reason_code:
            info.append(("Reason", doc.reason_code.name))
        if t == "SHIP" and doc.shipment_info:
            s = doc.shipment_info
            info += [
                ("Carrier", s.carrier or ""),
                ("Vehicle no.", s.vehicle_no or ""),
                ("Driver", " · ".join(x for x in (s.driver_name, s.driver_phone) if x)),
                ("Seal no.", s.seal_no or ""),
            ]
        if t == "COUNT" and doc.count_locations:
            codes = sorted(dl.location.code for dl in doc.count_locations)
            shown = ", ".join(codes[:30]) + (f" and {len(codes) - 30} more" if len(codes) > 30 else "")
            info.append(("Locations", shown))
        info.append(("Created", f"{self._time(doc.created_at)}  {self._user(doc.created_by)}".strip()))
        if doc.posted_at:
            info.append(("Posted", self._time(doc.posted_at)))
        return info

    def _lines(self, doc: DocumentHeader) -> tuple[list[Column], list[list[str]], str]:
        lines = list(doc.lines)
        t = doc.doc_type
        has_batch = any(line.batch_no for line in lines)
        has_expiry = any(line.expiry_date for line in lines)
        uom: LineValue = lambda line: line.uom.code  # noqa: E731
        # (column, value) pairs; the first quantity column marked as the total is summed per unit
        spec: list[tuple[Column, LineValue]] = [(Column("#", 0.35, "R"), lambda line: str(line.line_no))]
        total_of: LineValue | None = None

        def add(title: str, weight: float, value: LineValue, align: str = "L") -> None:
            spec.append((Column(title, weight, align), value))

        def item_columns() -> None:
            add("SKU", 1.3, lambda line: line.item.sku_code)
            add("Item", 2.6, lambda line: line.item.name)

        def tracking_columns() -> None:
            if has_batch:
                add("Batch", 1.1, lambda line: line.batch_no or "")
            if has_expiry:
                add("Expiry", 1.0, lambda line: _date(line.expiry_date))

        def qty(value: Callable[[DocumentLine], Decimal]) -> LineValue:
            return lambda line: qty_text(value(line))

        if t == "PO":
            item_columns()
            add("Unit", 0.6, uom)
            add("Ordered", 0.9, total_of := qty(lambda line: line.qty_planned), "R")
            add("Received", 0.9, qty(lambda line: line.qty_actual), "R")
            add("Open", 0.9, qty(lambda line: max(line.qty_planned - line.qty_actual, Decimal(0))), "R")
        elif t == "SO":
            progress = SalesOrderService(self.db, self.user.tenant_id, self.user.id).progress(doc)
            item_columns()
            add("Ordered", 0.9, total_of := qty(lambda line: line.qty_planned), "R")
            add("Unit", 0.6, uom)
            base = lambda line: f" {line.item.base_uom.code}"  # noqa: E731
            add("Picked", 1.0, lambda line: qty_text(progress[line.id].picked) + base(line), "R")
            add("Shipped", 1.0, lambda line: qty_text(progress[line.id].shipped) + base(line), "R")
        elif t == "GRN":
            item_columns()
            tracking_columns()
            add("Expected", 0.9, qty(lambda line: line.qty_planned), "R")
            add("Received", 0.9, total_of := qty(lambda line: line.qty_actual), "R")
            add("Unit", 0.6, uom)
        elif is_putaway_sheet(doc):
            # Scan the item, take it to the suggested bin (or any bin), scan the bin; the blanks are for paper use
            add("Item", 3.0, _item_barcode)
            tracking_columns()
            add("Qty", 0.7, total_of := qty(lambda line: line.qty_planned), "R")
            add("Unit", 0.5, uom)
            add("Suggested bin", 1.6, lambda line: "" if line.confirmed_at else (_bin_barcode(line.to_location) if line.to_location else "Any bin"), "C")
            add("Put in bin", 1.1, lambda line: _location(line.to_location) if line.confirmed_at else "", "C")
        elif t in ("PUTAWAY", "MOVE"):
            add("From", 1.2, lambda line: _location(line.from_location))
            item_columns()
            tracking_columns()
            add("Qty", 0.8, total_of := qty(lambda line: line.qty_actual), "R")
            add("Unit", 0.6, uom)
            add("To", 1.2, lambda line: _location(line.to_location))
        elif t == "PICK":
            # Route order: by bin, so the printed list walks the warehouse once
            lines.sort(key=lambda line: (_location(line.from_location), line.line_no))
            add("Bin", 1.4, lambda line: _bin_barcode(line.from_location), "C")
            add("Item", 3.0, _item_barcode)
            tracking_columns()
            add("To pick", 0.8, total_of := qty(lambda line: line.qty_planned), "R")
            # Blank until confirmed: room to write the picked quantity on the paper list
            add("Picked", 0.8, lambda line: qty_text(line.qty_actual) if line.confirmed_at else "", "R")
            add("Unit", 0.6, uom)
        elif t == "COUNT":
            lines.sort(key=lambda line: (_location(line.to_location), line.line_no))
            # A blind count sheet for counters who may not see the book quantity
            show_book = "cycle_count.view_expected" in self.user.permissions
            add("Location", 1.2, lambda line: _location(line.to_location))
            item_columns()
            tracking_columns()
            if show_book:
                add("Book", 0.8, qty(lambda line: line.qty_planned), "R")
            counted = lambda line: line.count_entries[-1].qty if line.count_entries else None  # noqa: E731
            add("Counted", 0.9, lambda line: qty_text(c) if (c := counted(line)) is not None else "", "R")
            if show_book:
                add("Difference", 0.9, lambda line: _signed(c - line.qty_planned) if (c := counted(line)) is not None else "", "R")
            add("Unit", 0.6, uom)
        elif t == "ADJUST":
            add("Location", 1.2, lambda line: _location(line.to_location))
            item_columns()
            tracking_columns()
            add("Change", 0.9, lambda line: _signed(line.qty_actual), "R")
            add("Unit", 0.6, uom)
        elif t == "REPACK":
            lines.sort(key=lambda line: (line.from_location_id is None, line.line_no))
            add("", 0.9, lambda line: "Consume" if line.from_location_id else "Produce")
            add("Location", 1.2, lambda line: _location(line.from_location or line.to_location))
            item_columns()
            tracking_columns()
            add("Qty", 0.8, qty(lambda line: line.qty_actual), "R")
            add("Unit", 0.6, uom)
        else:  # SHIP, RETURN_IN, RETURN_OUT
            if t == "RETURN_OUT" or t == "SHIP":
                add("From", 1.2, lambda line: _location(line.from_location))
            item_columns()
            tracking_columns()
            add("Qty", 0.8, total_of := qty(lambda line: line.qty_actual), "R")
            add("Unit", 0.6, uom)
            if t == "RETURN_IN":
                add("To", 1.2, lambda line: _location(line.to_location))

        columns = [c for c, _ in spec]
        rows = [[value(line) for _, value in spec] for line in lines]
        return columns, rows, self._totals(lines, total_of)

    @staticmethod
    def _totals(lines: list[DocumentLine], total_of: LineValue | None) -> str:
        count = f"{len(lines)} line{'' if len(lines) == 1 else 's'}"
        if total_of is None or not lines:
            return count
        per_unit: dict[str, Decimal] = defaultdict(Decimal)
        for line in lines:
            per_unit[line.uom.code] += Decimal(total_of(line))
        return f"{count} · Total " + ", ".join(f"{qty_text(q)} {u}" for u, q in per_unit.items())


def _signed(value: Decimal) -> str:
    return ("+" if value > 0 else "") + qty_text(value)

