"""Deleting master data: rows are removed from the database, not flagged.

A record that documents, stock or users still point at cannot be removed without breaking those records, so the delete is refused
with a message naming what uses it; the way out is to set the record inactive. The checks below give readable messages for the usual
cases, and the database's foreign keys remain the final word (anything they catch is refused the same way). The audit log keeps the
deleted record's last values."""

import uuid

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader, DocumentLine, DocumentLocation
from app.models.item import Item, ItemBarcode, ItemUomConversion
from app.models.location import Location
from app.models.reason_code import ReasonCode
from app.models.returnable_asset import ReturnableAssetTxn
from app.models.stock import StockBalance, StockLedger
from app.models.user import User

INACTIVE_HINT = "Set it inactive instead to hide it from new work."


def _doc_numbers(db: Session, tenant_id: uuid.UUID, *conditions, via_lines: bool = False) -> list[str]:
    """Documents of any status (finished ones included: they keep pointing at the record)"""
    stmt = select(DocumentHeader.doc_no).where(DocumentHeader.tenant_id == tenant_id)
    if via_lines:
        stmt = stmt.join(DocumentLine, DocumentLine.document_id == DocumentHeader.id)
    return list(db.scalars(stmt.where(*conditions).distinct().order_by(DocumentHeader.doc_no).limit(5)))


def _refuse_if_docs(what: str, docs: list[str]) -> None:
    if docs:
        more = " and others" if len(docs) == 5 else ""
        raise ConflictError(f"{what} is used by documents ({', '.join(docs)}{more}), so it cannot be deleted. {INACTIVE_HINT}")


def _exists(db: Session, stmt) -> bool:
    return db.scalar(stmt.limit(1)) is not None


def _remove(db: Session, obj, what: str) -> None:
    """Delete the row inside a savepoint, so a reference the checks missed fails cleanly instead of breaking the request"""
    try:
        with db.begin_nested():
            db.delete(obj)
            db.flush()
    except IntegrityError:
        raise ConflictError(f"{what} is still referenced by other records, so it cannot be deleted. {INACTIVE_HINT}") from None


def delete_item(db: Session, item: Item) -> None:
    what = f"Item {item.sku_code}"
    t = item.tenant_id
    if _exists(db, select(StockBalance.id).where(StockBalance.tenant_id == t, StockBalance.item_id == item.id)) or _exists(
        db, select(StockLedger.id).where(StockLedger.tenant_id == t, StockLedger.item_id == item.id)
    ):
        raise ConflictError(f"{what} has stock or stock history, so it cannot be deleted. {INACTIVE_HINT}")
    _refuse_if_docs(what, _doc_numbers(db, t, DocumentLine.item_id == item.id, via_lines=True))
    # Barcodes and unit conversions belong to the item and go with it
    db.execute(delete(ItemBarcode).where(ItemBarcode.tenant_id == t, ItemBarcode.item_id == item.id))
    db.execute(delete(ItemUomConversion).where(ItemUomConversion.tenant_id == t, ItemUomConversion.item_id == item.id))
    _remove(db, item, what)


def delete_location(db: Session, location: Location) -> None:
    what = f"Location {location.code}"
    t = location.tenant_id
    child = db.scalar(
        select(Location.code)
        .where(Location.tenant_id == t, Location.parent_id == location.id)
        .order_by(Location.is_deleted, Location.code)
        .limit(1)
    )
    if child is not None:
        raise ConflictError(f"{what} still contains other locations (such as {child}). Delete those first.")
    if _exists(db, select(StockBalance.id).where(StockBalance.tenant_id == t, StockBalance.location_id == location.id)) or _exists(
        db, select(StockLedger.id).where(StockLedger.tenant_id == t, StockLedger.location_id == location.id)
    ):
        raise ConflictError(f"{what} has stock or stock history, so it cannot be deleted. Lock it or set it inactive instead.")
    _refuse_if_docs(what, _doc_numbers(db, t, DocumentHeader.location_id == location.id))
    _refuse_if_docs(
        what,
        _doc_numbers(
            db, t, or_(DocumentLine.from_location_id == location.id, DocumentLine.to_location_id == location.id), via_lines=True
        ),
    )
    _refuse_if_docs(
        what,
        _doc_numbers(
            db, t, DocumentHeader.id.in_(select(DocumentLocation.document_id).where(DocumentLocation.location_id == location.id))
        ),
    )
    _remove(db, location, what)


def delete_partner(db: Session, partner: BusinessPartner) -> None:
    what = f"Business partner {partner.code}"
    t = partner.tenant_id
    _refuse_if_docs(what, _doc_numbers(db, t, DocumentHeader.partner_id == partner.id))
    user = db.scalar(select(User.username).where(User.tenant_id == t, User.partner_id == partner.id).limit(1))
    if user is not None:
        raise ConflictError(f"{what} is linked to user account {user}. Remove the link in Users first.")
    if _exists(db, select(ReturnableAssetTxn.id).where(ReturnableAssetTxn.tenant_id == t, ReturnableAssetTxn.partner_id == partner.id)):
        raise ConflictError(f"{what} has returnable asset history (pallets, crates…), so it cannot be deleted. {INACTIVE_HINT}")
    _remove(db, partner, what)


def delete_reason(db: Session, reason: ReasonCode) -> None:
    what = f"Reason code {reason.code}"
    _refuse_if_docs(what, _doc_numbers(db, reason.tenant_id, DocumentHeader.reason_code_id == reason.id))
    _remove(db, reason, what)
