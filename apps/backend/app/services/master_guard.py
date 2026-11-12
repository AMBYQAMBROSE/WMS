"""Checks before deleting master data: a record still in use must not disappear from under stock or open documents.

Deletes are soft (is_deleted), so history keeps its references; these checks only stop records that are still live from vanishing
from pickers and lists while stock or unfinished work points at them."""

import uuid

from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.models.document import DocumentHeader, DocumentLine
from app.models.location import Location
from app.models.returnable_asset import ReturnableAssetTxn
from app.models.stock import StockBalance
from app.models.user import User

# Document statuses after which a document no longer needs its master data to stay live
DONE_STATUSES = ("POSTED", "CANCELLED", "CLOSED", "SHIPPED", "RECEIVED")


def _open_doc_numbers(db: Session, tenant_id: uuid.UUID, *conditions, via_lines: bool = False) -> list[str]:
    stmt = select(DocumentHeader.doc_no).where(
        DocumentHeader.tenant_id == tenant_id,
        DocumentHeader.is_deleted == false(),
        DocumentHeader.status.not_in(DONE_STATUSES),
    )
    if via_lines:
        stmt = stmt.join(DocumentLine, DocumentLine.document_id == DocumentHeader.id).where(DocumentLine.is_deleted == false())
    return list(db.scalars(stmt.where(*conditions).distinct().order_by(DocumentHeader.doc_no).limit(5)))


def _refuse_if_open_docs(what: str, docs: list[str]) -> None:
    if docs:
        more = " and others" if len(docs) == 5 else ""
        raise ConflictError(
            f"{what} is used by open documents ({', '.join(docs)}{more}). Finish or cancel them first, or set it inactive instead."
        )


def _has_stock(db: Session, tenant_id: uuid.UUID, *conditions) -> bool:
    return (
        db.scalar(
            select(StockBalance.id)
            .where(
                StockBalance.tenant_id == tenant_id,
                or_(StockBalance.qty_on_hand != 0, StockBalance.qty_allocated != 0),
                *conditions,
            )
            .limit(1)
        )
        is not None
    )


def check_item_deletable(db: Session, tenant_id: uuid.UUID, item_id: uuid.UUID, label: str) -> None:
    what = f"Item {label}"
    if _has_stock(db, tenant_id, StockBalance.item_id == item_id):
        raise ConflictError(f"{what} still has stock. Adjust or ship it to zero first, or set the item inactive instead.")
    _refuse_if_open_docs(what, _open_doc_numbers(db, tenant_id, DocumentLine.item_id == item_id, via_lines=True))


def check_location_deletable(db: Session, tenant_id: uuid.UUID, location_id: uuid.UUID, label: str) -> None:
    what = f"Location {label}"
    child = db.scalar(
        select(Location.code)
        .where(Location.tenant_id == tenant_id, Location.parent_id == location_id, Location.is_deleted == false())
        .limit(1)
    )
    if child is not None:
        raise ConflictError(f"{what} still contains other locations (such as {child}). Delete or empty those first.")
    if _has_stock(db, tenant_id, StockBalance.location_id == location_id):
        raise ConflictError(f"{what} still holds stock. Move it elsewhere first, or lock the location instead.")
    _refuse_if_open_docs(what, _open_doc_numbers(db, tenant_id, DocumentHeader.location_id == location_id))
    _refuse_if_open_docs(
        what,
        _open_doc_numbers(
            db,
            tenant_id,
            or_(DocumentLine.from_location_id == location_id, DocumentLine.to_location_id == location_id),
            via_lines=True,
        ),
    )


def check_partner_deletable(db: Session, tenant_id: uuid.UUID, partner_id: uuid.UUID, label: str) -> None:
    what = f"Business partner {label}"
    _refuse_if_open_docs(what, _open_doc_numbers(db, tenant_id, DocumentHeader.partner_id == partner_id))
    user = db.scalar(
        select(User.username)
        .where(User.tenant_id == tenant_id, User.partner_id == partner_id, User.is_deleted == false())
        .limit(1)
    )
    if user is not None:
        raise ConflictError(f"{what} is linked to user account {user}. Remove the link in Users first.")
    outstanding = db.scalar(
        select(func.coalesce(func.sum(ReturnableAssetTxn.qty_change), 0)).where(
            ReturnableAssetTxn.tenant_id == tenant_id,
            ReturnableAssetTxn.partner_id == partner_id,
            ReturnableAssetTxn.is_deleted == false(),
        )
    )
    if outstanding:
        raise ConflictError(f"{what} still has returnable assets (pallets, crates…) outstanding. Record their return first.")


def check_reason_deletable(db: Session, tenant_id: uuid.UUID, reason_id: uuid.UUID, label: str) -> None:
    _refuse_if_open_docs(f"Reason code {label}", _open_doc_numbers(db, tenant_id, DocumentHeader.reason_code_id == reason_id))
