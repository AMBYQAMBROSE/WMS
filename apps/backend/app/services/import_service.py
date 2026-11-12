"""Go-live data import: items, locations, business partners, opening stock (Excel .xlsx or CSV).

Flow: validate first (commit=False) and return row-level errors without writing; only when there are no errors import (commit=True)
as one transaction, so either everything takes effect or nothing does. Master data is matched by code (update if it exists, else create);
opening stock becomes one posted stock adjustment (reason: opening stock) that goes through the same posting logic (locks, freeze checks, ledger).
"""

import csv
import io
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError
from app.models.business_partner import BusinessPartner
from app.models.item import Item, ItemUomConversion, Uom
from app.models.location import LOCATION_TYPES, STOCK_LOCATION_TYPES, Location
from app.models.reason_code import REASON_CATEGORY_ADJUST, ReasonCode
from app.schemas.document import AdjustmentIn, AdjustmentLineIn
from app.schemas.document import PurchaseOrderIn, PurchaseOrderLineIn
from app.schemas.outbound import SalesOrderIn, SalesOrderLineIn
from app.services.adjustment_service import AdjustmentService
from app.services.purchase_order_service import PurchaseOrderService
from app.services.sales_order_service import SalesOrderService

MAX_ROWS = 100_000
# One order import creates at most this many orders (each one is a separate document with its own number)
MAX_ORDERS = 2_000
MAX_ERRORS = 200
OPENING_REASON = ("OPENING", "Opening stock")

YES = {"y", "yes", "true", "1", "Y", "YES", "Yes", "TRUE", "True"}
NO = {"n", "no", "false", "0", "", "N", "NO", "No", "FALSE", "False"}
LOCATION_TYPE_NAMES = {"Warehouse": "WAREHOUSE", "Zone": "ZONE", "Aisle": "AISLE", "Rack": "RACK", "Bin": "BIN", "Dock": "DOCK"}
PARTNER_TYPE_NAMES = {"Customer": "customer", "Supplier": "supplier", "Both": "both"}


class RowError(ValueError):
    pass


# ---------------------------------------------------------------- field parsing


def text(max_len: int) -> Callable[[object], str | None]:
    def parse(value):
        if value is None:
            return None
        # Excel reads purely numeric codes (e.g. barcodes) as numbers; turn them back into text without ".0"
        s = format(value, "f").rstrip("0").rstrip(".") if isinstance(value, float) else str(value)
        s = s.strip()
        if len(s) > max_len:
            raise RowError(f"Longer than {max_len} characters")
        return s or None
    return parse


def boolean(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip()
    if s in YES:
        return True
    if s in NO:
        return False
    raise RowError("Enter Yes or No")


def number(value) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise RowError("Not a number") from exc


def integer(value) -> int | None:
    n = number(value)
    if n is None:
        return None
    if n != n.to_integral_value():
        raise RowError("Must be a whole number")
    return int(n)


def day(value) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip().replace("/", "-").replace(".", "-")
    try:
        return date.fromisoformat(s if len(s) != 8 or "-" in s else f"{s[:4]}-{s[4:6]}-{s[6:]}")
    except ValueError as exc:
        raise RowError("Date must look like 2026-01-31") from exc


def choice(mapping: dict[str, str], allowed: tuple[str, ...] | set[str]) -> Callable[[object], str | None]:
    def parse(value):
        if value is None or str(value).strip() == "":
            return None
        s = str(value).strip()
        result = mapping.get(s, s.upper() if s.upper() in allowed else s.lower())
        if result not in allowed:
            raise RowError(f"Allowed values: {', '.join(mapping)}")
        return result
    return parse


@dataclass
class Column:
    key: str
    header: str
    parse: Callable[[object], object]
    required: bool = False
    help: str = ""
    example: object = None


@dataclass
class ImportKind:
    key: str
    name: str
    permissions: tuple[str, ...]
    columns: list[Column]
    notes: list[str] = field(default_factory=list)


def _order_columns(partner: str, partner_example: str, date_header: str) -> list[Column]:
    return [
        Column("order_ref", "Order ref", text(50), False,
               "Rows with the same ref become one order. Leave empty to make one order per "
               f"{partner.lower()}, date and remark", "ORD-001"),
        Column("partner_code", f"{partner} code", text(50), True, f"A {partner.lower()} already in the system", partner_example),
        Column("sku_code", "SKU code", text(50), True, "An active item already in the system", "A1001"),
        Column("qty", "Quantity", number, True, "Greater than 0, in the unit below", 24),
        Column("uom_code", "Unit", text(20), False, "Defaults to the item's base unit; other units need a conversion on the item", "EA"),
        Column("expected_date", date_header, day, False, "Format 2026-12-31; the same for every row of one order", "2026-12-31"),
        Column("remark", "Remark", text(400), False, "The same for every row of one order", ""),
    ]


ORDER_NOTES = [
    "Each order is created as a draft; review it, then confirm it (one by one, or several at once from the list)",
    "Order ref, partner, date and remark must be the same on every row of one order",
    "The same item and unit twice in one order is merged into one line",
]


KINDS: dict[str, ImportKind] = {
    "items": ImportKind(
        "items", "Items", ("item.create", "item.update"),
        [
            Column("sku_code", "SKU code", text(50), True, "Unique; updated if it already exists", "A1001"),
            Column("name", "Item name", text(200), True, "", "Spring water 550ml"),
            Column("base_uom_code", "Base unit", text(20), True, "Unit of measure code already in the system, e.g. EA, CTN", "EA"),
            Column("barcode", "Barcode", text(50), False, "Main barcode; format the column as text in Excel to avoid scientific notation", "6901234567890"),
            Column("category", "Category", text(100), False, "", "Beverages"),
            Column("is_batch_managed", "Batch managed", boolean, False, "Yes/No, default No", "No"),
            Column("is_expiry_managed", "Expiry managed", boolean, False, "Yes/No, default No", "Yes"),
            Column("shelf_life_days", "Shelf life (days)", integer, False, "", 365),
            Column("is_active", "Active", boolean, False, "Yes/No, default Yes", "Yes"),
        ],
    ),
    "locations": ImportKind(
        "locations", "Locations", ("location.create", "location.update"),
        [
            Column("code", "Location code", text(50), True, "Unique; updated if it already exists", "A01-01-01"),
            Column("name", "Location name", text(100), True, "", "Zone A row 01 level 01"),
            Column("location_type", "Type", choice(LOCATION_TYPE_NAMES, LOCATION_TYPES), True,
                   "Warehouse/Zone/Aisle/Rack/Bin/Dock; only bins and docks can hold stock", "Bin"),
            Column("parent_code", "Parent location code", text(50), False, "An existing location or another row in this file", "A01"),
            Column("is_pickable", "Pickable", boolean, False, "Yes/No, default No; allocation prefers pickable bins", "Yes"),
            Column("is_locked", "Locked", boolean, False, "Yes/No, default No", "No"),
            Column("is_active", "Active", boolean, False, "Yes/No, default Yes", "Yes"),
        ],
        ["The parent of an existing location cannot be changed by import (it would change the paths below it); change it in the UI"],
    ),
    "partners": ImportKind(
        "partners", "Business partners", ("business_partner.create", "business_partner.update"),
        [
            Column("code", "Code", text(50), True, "Unique; updated if it already exists", "C0001"),
            Column("name", "Name", text(200), True, "", "Main Street Supermarket"),
            Column("partner_type", "Type", choice(PARTNER_TYPE_NAMES, {"customer", "supplier", "both"}), True,
                   "Customer/Supplier/Both", "Customer"),
            Column("contact_name", "Contact", text(100), False, "", "John Smith"),
            Column("contact_phone", "Phone", text(50), False, "", "13800000000"),
            Column("address", "Address", text(400), False, "", "1 Main Street"),
            Column("is_active", "Active", boolean, False, "Yes/No, default Yes", "Yes"),
        ],
    ),
    "opening_stock": ImportKind(
        "opening_stock", "Opening stock", ("adjustment.create", "adjustment.post"),
        [
            Column("sku_code", "SKU code", text(50), True, "An item already in the system", "A1001"),
            Column("location_code", "Location code", text(50), True, "A bin or dock", "A01-01-01"),
            Column("qty", "Quantity", number, True, "Greater than 0, in the unit below", 120),
            Column("uom_code", "Unit", text(20), False, "Defaults to the item's base unit", "EA"),
            Column("batch_no", "Batch no.", text(50), False, "Required for batch-managed items", "L20261001"),
            Column("expiry_date", "Expiry date", day, False, "Required for expiry-managed items, format 2027-10-01", "2027-10-01"),
        ],
        ["Importing creates one posted stock adjustment (reason: opening stock), visible under Stock adjustments", "Rows with the same item, location, batch and expiry are merged"],
    ),
    "purchase_orders": ImportKind(
        "purchase_orders", "Purchase orders", ("purchase_order.create",),
        _order_columns("Supplier", "S0001", "Expected date"), ORDER_NOTES,
    ),
    "sales_orders": ImportKind(
        "sales_orders", "Sales orders", ("sales_order.create",),
        _order_columns("Customer", "C0001", "Requested ship date"), ORDER_NOTES,
    ),
}


@dataclass
class ImportResult:
    kind: str
    total: int = 0
    created: int = 0
    updated: int = 0
    errors: list[dict] = field(default_factory=list)
    error_count: int = 0
    warnings: list[str] = field(default_factory=list)
    committed: bool = False
    document_id: uuid.UUID | None = None
    document_no: str | None = None
    # Order imports: the orders created (or, when validating, to be created): ref, partner, lines, and number once created
    documents: list[dict] = field(default_factory=list)

    def error(self, row: int, column: str, message: str) -> None:
        self.error_count += 1
        if len(self.errors) < MAX_ERRORS:
            self.errors.append({"row": row, "column": column, "message": message})


# ---------------------------------------------------------------- reading files


def _read_rows(filename: str, content: bytes) -> list[list[object]]:
    name = filename.lower()
    if name.endswith(".xlsx"):
        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 - corrupt file, not xlsx, etc.
            raise DomainError("Cannot read the Excel file; make sure it is in .xlsx format") from exc
        ws = wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if name.endswith(".csv"):
        # A CSV saved by Excel on a Chinese-locale Windows is usually GBK
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                decoded = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise DomainError("Unrecognized CSV encoding; save it as UTF-8")
        return [[c if c != "" else None for c in r] for r in csv.reader(io.StringIO(decoded))]
    raise DomainError("Only .xlsx and .csv files are supported")


def parse_file(kind: ImportKind, filename: str, content: bytes, result: ImportResult) -> tuple[list[tuple[int, dict]], set[str]]:
    rows = _read_rows(filename, content)
    # Skip leading blank rows; the first non-blank row is the header, columns are matched by header text or field name (any order)
    while rows and all(c is None or str(c).strip() == "" for c in rows[0]):
        rows.pop(0)
    if not rows:
        raise DomainError("The file is empty")
    header = [str(c).strip().rstrip("*") if c is not None else "" for c in rows[0]]
    index = {}
    for col in kind.columns:
        for i, h in enumerate(header):
            if h in (col.header, col.key):
                index[col.key] = i
    missing = [c.header for c in kind.columns if c.required and c.key not in index]
    if missing:
        raise DomainError(f"Missing required columns: {', '.join(missing)} (use the template and keep its header row)")
    parsed = []
    for n, raw in enumerate(rows[1:], start=2):
        if all(c is None or str(c).strip() == "" for c in raw):
            continue
        if len(parsed) >= MAX_ROWS:
            raise DomainError(f"At most {MAX_ROWS} rows per import; split the file")
        record, ok = {}, True
        for col in kind.columns:
            value = raw[index[col.key]] if col.key in index and index[col.key] < len(raw) else None
            try:
                record[col.key] = col.parse(value)
            except RowError as exc:
                result.error(n, col.header, str(exc))
                ok = False
                continue
            if col.required and record[col.key] is None:
                result.error(n, col.header, "Required")
                ok = False
        if ok:
            parsed.append((n, record))
    result.total = len(parsed) + len({e["row"] for e in result.errors})
    return parsed, set(index)


# ---------------------------------------------------------------- import kinds


def _duplicates(rows: list[tuple[int, dict]], key: str, header: str, result: ImportResult) -> list[tuple[int, dict]]:
    seen: dict[str, int] = {}
    unique = []
    for n, r in rows:
        k = r[key].upper()
        if k in seen:
            result.error(n, header, f"Duplicate of row {seen[k]}")
            continue
        seen[k] = n
        unique.append((n, r))
    return unique


def _existing(db: Session, model, code_attr, tenant_id: uuid.UUID) -> dict[str, object]:
    return {getattr(o, code_attr).upper(): o for o in db.scalars(
        select(model).where(model.tenant_id == tenant_id, model.is_deleted == false())
    )}


class ImportService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def run(self, kind_key: str, filename: str, content: bytes, commit: bool) -> ImportResult:
        kind = KINDS[kind_key]
        result = ImportResult(kind=kind_key)
        rows, self.present = parse_file(kind, filename, content, result)
        # With any error, only validate and never write; each handler checks again before writing
        getattr(self, f"_{kind_key}")(rows, result, commit and result.error_count == 0)
        return result

    def _assign(self, obj, record: dict, defaults: dict, is_new: bool) -> None:
        """New records get defaults for empty cells; updates only change columns present in the file and keep the rest"""
        for key, default in defaults.items():
            if is_new:
                value = record.get(key)
                setattr(obj, key, default if value is None else value)
            elif key in self.present:
                value = record[key]
                setattr(obj, key, default if value is None and isinstance(default, bool) else value)

    def _audit(self, obj):
        obj.updated_by = self.user_id
        if obj.created_by is None:
            obj.created_by = self.user_id

    # ---- items
    def _items(self, rows, result: ImportResult, write: bool) -> None:
        rows = _duplicates(rows, "sku_code", "SKU code", result)
        uoms = {u.code.upper(): u for u in self.db.scalars(select(Uom).where(Uom.tenant_id == self.tenant_id))}
        existing = _existing(self.db, Item, "sku_code", self.tenant_id)
        planned = []
        for n, r in rows:
            uom = uoms.get(r["base_uom_code"].upper())
            if uom is None:
                result.error(n, "Base unit", f"Unit {r['base_uom_code']} does not exist")
                continue
            item = existing.get(r["sku_code"].upper())
            if item is not None and item.base_uom_id != uom.id:
                result.error(n, "Base unit", "The base unit of an existing item cannot be changed by import (it affects existing stock and documents)")
                continue
            planned.append((r, uom, item))
        if not write or result.error_count:
            result.created = sum(1 for _, _, i in planned if i is None)
            result.updated = len(planned) - result.created
            return
        for r, uom, item in planned:
            if item is None:
                item = Item(tenant_id=self.tenant_id, sku_code=r["sku_code"], base_uom_id=uom.id, created_by=self.user_id)
                self.db.add(item)
                result.created += 1
            else:
                result.updated += 1
            is_new = item.id is None
            item.name = r["name"]
            self._assign(item, r, {"barcode": None, "category": None, "is_batch_managed": False,
                                   "is_expiry_managed": False, "shelf_life_days": None, "is_active": True}, is_new)
            self._audit(item)
        self.db.flush()
        result.committed = True

    # ---- business partners
    def _partners(self, rows, result: ImportResult, write: bool) -> None:
        rows = _duplicates(rows, "code", "Code", result)
        existing = _existing(self.db, BusinessPartner, "code", self.tenant_id)
        if not write or result.error_count:
            result.created = sum(1 for _, r in rows if r["code"].upper() not in existing)
            result.updated = len(rows) - result.created
            return
        for _, r in rows:
            partner = existing.get(r["code"].upper())
            if partner is None:
                partner = BusinessPartner(tenant_id=self.tenant_id, code=r["code"], created_by=self.user_id)
                self.db.add(partner)
                result.created += 1
            else:
                result.updated += 1
            partner.name, partner.partner_type = r["name"], r["partner_type"]
            self._assign(partner, r, {"contact_name": None, "contact_phone": None, "address": None, "is_active": True},
                         partner.id is None)
            self._audit(partner)
        self.db.flush()
        result.committed = True

    # ---- locations (parents may be in the same file; written in hierarchy order)
    def _locations(self, rows, result: ImportResult, write: bool) -> None:
        rows = _duplicates(rows, "code", "Location code", result)
        existing = _existing(self.db, Location, "code", self.tenant_id)
        in_file = {r["code"].upper(): (n, r) for n, r in rows}
        code_by_id = {o.id: c for c, o in existing.items()}
        valid = []
        for n, r in rows:
            parent = (r["parent_code"] or "").upper()
            if parent and parent not in existing and parent not in in_file:
                result.error(n, "Parent location code", f"Parent location {r['parent_code']} does not exist")
                continue
            if parent == r["code"].upper():
                result.error(n, "Parent location code", "Cannot be its own parent")
                continue
            old = existing.get(r["code"].upper())
            if old is not None:
                old_parent = code_by_id.get(old.parent_id, "") if old.parent_id else ""
                if old_parent != parent:
                    result.error(n, "Parent location code", "The parent of an existing location cannot be changed by import")
                    continue
            valid.append((n, r))
        # Order by hierarchy: parents first; detect cycles
        ordered, placed, pending = [], set(existing), list(valid)
        while pending:
            progressed = False
            for entry in list(pending):
                parent = (entry[1]["parent_code"] or "").upper()
                if not parent or parent in placed:
                    ordered.append(entry)
                    placed.add(entry[1]["code"].upper())
                    pending.remove(entry)
                    progressed = True
            if not progressed:
                for n, _ in pending:
                    result.error(n, "Parent location code", "Parent chain contains a cycle, or the parent itself has errors")
                break
        if not write or result.error_count:
            result.created = sum(1 for _, r in ordered if r["code"].upper() not in existing)
            result.updated = len(ordered) - result.created
            return
        by_code = dict(existing)
        for _, r in ordered:
            code = r["code"].upper()
            loc = by_code.get(code)
            parent = by_code.get((r["parent_code"] or "").upper()) if r["parent_code"] else None
            if loc is None:
                loc = Location(
                    tenant_id=self.tenant_id, code=r["code"], parent_id=parent.id if parent else None,
                    path=f"{parent.path if parent else ''}/{r['code']}", created_by=self.user_id,
                )
                self.db.add(loc)
                by_code[code] = loc
                result.created += 1
            else:
                result.updated += 1
            loc.name, loc.location_type = r["name"], r["location_type"]
            self._assign(loc, r, {"is_pickable": False, "is_locked": False, "is_active": True}, loc.id is None)
            self._audit(loc)
            # The next row may use this one as its parent, so its key and path are needed now
            self.db.flush()
        result.committed = True

    # ---- opening stock: one posted stock adjustment
    def _opening_stock(self, rows, result: ImportResult, write: bool) -> None:
        items = _existing(self.db, Item, "sku_code", self.tenant_id)
        locations = _existing(self.db, Location, "code", self.tenant_id)
        uoms = {u.code.upper(): u for u in self.db.scalars(select(Uom).where(Uom.tenant_id == self.tenant_id))}
        merged: dict[tuple, AdjustmentLineIn] = {}
        for n, r in rows:
            item = items.get(r["sku_code"].upper())
            if item is None or not item.is_active:
                result.error(n, "SKU code", f"Item {r['sku_code']} does not exist or is inactive")
                continue
            loc = locations.get(r["location_code"].upper())
            if loc is None or not loc.is_active:
                result.error(n, "Location code", f"Location {r['location_code']} does not exist or is inactive")
                continue
            if loc.location_type not in STOCK_LOCATION_TYPES:
                result.error(n, "Location code", "Only bins and docks can hold stock")
                continue
            if r["qty"] <= 0:
                result.error(n, "Quantity", "Must be greater than 0")
                continue
            uom_id = item.base_uom_id
            if r["uom_code"]:
                uom = uoms.get(r["uom_code"].upper())
                if uom is None:
                    result.error(n, "Unit", f"Unit {r['uom_code']} does not exist")
                    continue
                uom_id = uom.id
            if item.is_batch_managed and not r["batch_no"]:
                result.error(n, "Batch no.", "Required: this item is batch managed")
                continue
            if item.is_expiry_managed and not r["expiry_date"]:
                result.error(n, "Expiry date", "Required: this item is expiry managed")
                continue
            batch = r["batch_no"] if item.is_batch_managed else None
            expiry = r["expiry_date"] if item.is_expiry_managed else None
            key = (item.id, loc.id, uom_id, batch, expiry)
            if key in merged:
                merged[key].qty += r["qty"]
            else:
                merged[key] = AdjustmentLineIn(item_id=item.id, uom_id=uom_id, location_id=loc.id, qty=r["qty"],
                                               batch_no=batch, expiry_date=expiry)
        result.created = len(merged)
        if not merged:
            if not result.error_count:
                result.error(0, "", "No rows to import")
            return
        if not write or result.error_count:
            return
        reason = self.db.scalars(select(ReasonCode).where(
            ReasonCode.tenant_id == self.tenant_id, ReasonCode.category == REASON_CATEGORY_ADJUST,
            ReasonCode.code == OPENING_REASON[0])).first()
        if reason is None:
            reason = ReasonCode(tenant_id=self.tenant_id, category=REASON_CATEGORY_ADJUST, code=OPENING_REASON[0],
                                name=OPENING_REASON[1], created_by=self.user_id, updated_by=self.user_id)
            self.db.add(reason)
            self.db.flush()
        svc = AdjustmentService(self.db, self.tenant_id, self.user_id)
        doc = svc.create(AdjustmentIn(reason_code_id=reason.id, remark="Opening stock import", lines=list(merged.values())))
        svc.post(doc.id)
        result.committed = True
        result.document_id = doc.id
        result.document_no = doc.doc_no

    # ---- purchase / sales orders: rows grouped into draft orders
    def _purchase_orders(self, rows, result: ImportResult, write: bool) -> None:
        self._orders(rows, result, write, supplier=True)

    def _sales_orders(self, rows, result: ImportResult, write: bool) -> None:
        self._orders(rows, result, write, supplier=False)

    def _orders(self, rows, result: ImportResult, write: bool, supplier: bool) -> None:
        partner_header = "Supplier code" if supplier else "Customer code"
        date_header = "Expected date" if supplier else "Requested ship date"
        roles = ("supplier", "both") if supplier else ("customer", "both")
        partners = _existing(self.db, BusinessPartner, "code", self.tenant_id)
        items = _existing(self.db, Item, "sku_code", self.tenant_id)
        uoms = {u.code.upper(): u for u in self.db.scalars(select(Uom).where(Uom.tenant_id == self.tenant_id))}
        # (item, unit) pairs that convert to the item's base unit, so a wrong unit is reported per row before anything is written
        convertible = {(item_id, uom_id) for item_id, uom_id in self.db.execute(
            select(ItemUomConversion.item_id, ItemUomConversion.from_uom_id)
            .join(Item, Item.id == ItemUomConversion.item_id)
            .where(ItemUomConversion.tenant_id == self.tenant_id, ItemUomConversion.is_deleted == false(),
                   ItemUomConversion.to_uom_id == Item.base_uom_id)
        )}

        orders: dict[tuple, dict] = {}
        for n, r in rows:
            partner = partners.get(r["partner_code"].upper())
            if partner is None or not partner.is_active:
                result.error(n, partner_header, f"{r['partner_code']} does not exist or is inactive")
                continue
            if partner.partner_type not in roles:
                result.error(n, partner_header, f"{partner.code} is not a {'supplier' if supplier else 'customer'}")
                continue
            item = items.get(r["sku_code"].upper())
            if item is None or not item.is_active:
                result.error(n, "SKU code", f"Item {r['sku_code']} does not exist or is inactive")
                continue
            if r["qty"] <= 0:
                result.error(n, "Quantity", "Must be greater than 0")
                continue
            if r["qty"] != round(r["qty"], 4):
                result.error(n, "Quantity", "At most 4 decimal places")
                continue
            uom_id = item.base_uom_id
            if r["uom_code"]:
                uom = uoms.get(r["uom_code"].upper())
                if uom is None:
                    result.error(n, "Unit", f"Unit {r['uom_code']} does not exist")
                    continue
                if uom.id != item.base_uom_id and (item.id, uom.id) not in convertible:
                    result.error(n, "Unit", f"Item {item.sku_code} has no conversion from {uom.code} to its base unit")
                    continue
                uom_id = uom.id
            ref = (r["order_ref"] or "").upper()
            key = ("ref", ref) if ref else ("auto", partner.id, r["expected_date"], r["remark"] or "")
            order = orders.get(key)
            if order is None:
                if len(orders) >= MAX_ORDERS:
                    raise DomainError(f"At most {MAX_ORDERS} orders per import; split the file")
                order = orders[key] = {
                    "row": n, "ref": r["order_ref"], "partner": partner, "expected_date": r["expected_date"],
                    "remark": r["remark"], "lines": {},
                }
            else:
                # One order has one header: a row that disagrees with the order's first row is an error, not a silent pick
                mismatch = next((
                    header for field_key, header, value in (
                        ("partner", partner_header, partner), ("expected_date", date_header, r["expected_date"]),
                        ("remark", "Remark", r["remark"]),
                    ) if order[field_key] != value
                ), None)
                if mismatch:
                    result.error(n, mismatch, f"Differs from row {order['row']} of order {r['order_ref']}")
                    continue
            lines = order["lines"]
            lines[(item.id, uom_id)] = lines.get((item.id, uom_id), Decimal(0)) + r["qty"]

        result.created = len(orders)
        result.documents = [
            {"ref": o["ref"], "partner": f"{o['partner'].code} {o['partner'].name}", "lines": len(o["lines"]),
             "document_id": None, "document_no": None}
            for o in orders.values()
        ]
        if not orders:
            if not result.error_count:
                result.error(0, "", "No rows to import")
            return
        if not write or result.error_count:
            return
        service = PurchaseOrderService if supplier else SalesOrderService
        schema, line_schema = (PurchaseOrderIn, PurchaseOrderLineIn) if supplier else (SalesOrderIn, SalesOrderLineIn)
        svc = service(self.db, self.tenant_id, self.user_id)
        for summary, order in zip(result.documents, orders.values()):
            doc = svc.create(schema(
                partner_id=order["partner"].id, expected_date=order["expected_date"], remark=order["remark"],
                lines=[line_schema(item_id=i, uom_id=u, qty=q) for (i, u), q in order["lines"].items()],
            ))
            summary["document_id"], summary["document_no"] = doc.id, doc.doc_no
        result.committed = True


# ---------------------------------------------------------------- template


def template(kind_key: str) -> bytes:
    kind = KINDS[kind_key]
    wb = Workbook()
    ws = wb.active
    ws.title = kind.name
    ws.append([c.header + ("*" if c.required else "") for c in kind.columns])
    ws.append([c.example for c in kind.columns])
    bold, fill = Font(bold=True), PatternFill("solid", fgColor="FFF2CC")
    for i, col in enumerate(kind.columns, start=1):
        cell = ws.cell(row=1, column=i)
        cell.font = bold
        if col.required:
            cell.fill = fill
        ws.column_dimensions[cell.column_letter].width = max(12, len(col.header) + 4)
        # Treat codes and barcodes as text so Excel does not turn long numbers into scientific notation
        if col.parse not in (number, integer, boolean, day):
            for row in range(2, 1002):
                ws.cell(row=row, column=i).number_format = "@"
    notes = wb.create_sheet("Notes")
    notes.append(["Column", "Required", "Notes"])
    for c in notes[1]:
        c.font = bold
    for col in kind.columns:
        notes.append([col.header, "Yes" if col.required else "", col.help])
    notes.append([])
    for line in ["Row 1 is the header, do not change it; row 2 is an example, delete it before importing.", "Click Validate first; when there are no errors click Import.", *kind.notes]:
        notes.append([line])
    notes.column_dimensions["A"].width = 18
    notes.column_dimensions["C"].width = 70
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
