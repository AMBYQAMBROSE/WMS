import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import case, false, or_, select, true
from sqlalchemy.orm import Session, joinedload

from app.core.errors import DomainError
from app.models.document import DocumentHeader, DocumentLine, DocumentLocation
from app.models.item import Item, ItemUomConversion
from app.models.location import Location
from app.models.stock import StockBalance, StockLedger
from app.services.document_common import (
    COUNT_IN_PROGRESS,
    DOC_COUNT,
    LOCK_RANGE,
    LOCK_ROW,
    utcnow,
)

MOVE_RECEIVE = "RECEIVE"
MOVE_PUTAWAY_OUT = "PUTAWAY_OUT"
MOVE_PUTAWAY_IN = "PUTAWAY_IN"
MOVE_MOVE_OUT = "MOVE_OUT"
MOVE_MOVE_IN = "MOVE_IN"
MOVE_ADJUST_IN = "ADJUST_IN"
MOVE_ADJUST_OUT = "ADJUST_OUT"
MOVE_COUNT_GAIN = "COUNT_GAIN"
MOVE_COUNT_LOSS = "COUNT_LOSS"
MOVE_PICK_OUT = "PICK_OUT"
MOVE_PICK_IN = "PICK_IN"
MOVE_SHIP_OUT = "SHIP_OUT"
MOVE_RETURN_IN = "RETURN_IN"
MOVE_RETURN_OUT = "RETURN_OUT"
MOVE_REPACK_OUT = "REPACK_OUT"
MOVE_REPACK_IN = "REPACK_IN"


@dataclass(frozen=True)
class Movement:
    item_id: uuid.UUID
    location_id: uuid.UUID
    batch_no: str | None
    expiry_date: date | None
    qty_change: Decimal
    movement_type: str
    ref_line_id: uuid.UUID | None
    # Allocation change moving with the quantity: + when allocating outbound, - when posting or cancelling picks; only pick-related movements carry it
    allocated_change: Decimal = Decimal(0)


def to_base_qty(
    db: Session, tenant_id: uuid.UUID, item: Item, uom_id: uuid.UUID, qty: Decimal
) -> Decimal:
    if uom_id == item.base_uom_id:
        return qty
    conversion = db.scalars(
        select(ItemUomConversion).where(
            ItemUomConversion.tenant_id == tenant_id,
            ItemUomConversion.item_id == item.id,
            ItemUomConversion.from_uom_id == uom_id,
            ItemUomConversion.to_uom_id == item.base_uom_id,
            ItemUomConversion.is_deleted == false(),
        )
    ).first()
    if conversion is None:
        raise DomainError(f"Item {item.sku_code} has no conversion from this unit to its base unit")
    return qty * conversion.factor


def _lock_key(m: Movement) -> tuple:
    return stock_key(m.item_id, m.location_id, m.batch_no, m.expiry_date)


def stock_key(item_id, location_id, batch_no, expiry_date) -> tuple:
    """Common sort key for locking balance rows: everything that locks several balances sorts by it to avoid deadlocks"""
    return (str(item_id), str(location_id), batch_no or "", str(expiry_date or ""))


def locked_balance_qty(
    db: Session,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
    batch_no: str | None,
    expiry_date: date | None,
) -> Decimal:
    """Read current balances and lock them until the transaction ends (used to compute count differences at posting)"""
    balance = db.scalars(
        select(StockBalance)
        .with_hint(StockBalance, LOCK_RANGE, "mssql")
        .where(
            StockBalance.tenant_id == tenant_id,
            StockBalance.item_id == item_id,
            StockBalance.location_id == location_id,
            StockBalance.batch_no == batch_no,
            StockBalance.expiry_date == expiry_date,
        )
        .execution_options(populate_existing=True)
    ).first()
    return balance.qty_on_hand if balance else Decimal(0)


def allocatable_balances(
    db: Session,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    today: date,
    source_location_id: uuid.UUID | None = None,
) -> list[StockBalance]:
    """Candidate stock for outbound allocation, taking update locks on the balances read (concurrent allocations of an item queue up and never double-reserve).

    Normal: bins (BIN) only; cross-dock: only the given receiving dock (DOCK) source_location_id.
    Always excluded: locked/inactive locations, locations being counted, expired batches.
    Order: first expiry first out (no expiry last) -> pickable bins first -> first in first out -> location code.
    """
    location_filter = (
        Location.id == source_location_id
        if source_location_id is not None
        else Location.location_type == "BIN"
    )
    counting = (
        select(DocumentLocation.location_id)
        .join(DocumentHeader, DocumentHeader.id == DocumentLocation.document_id)
        .where(
            DocumentHeader.tenant_id == tenant_id,
            DocumentHeader.doc_type == DOC_COUNT,
            DocumentHeader.status == COUNT_IN_PROGRESS,
        )
    )
    stmt = (
        select(StockBalance)
        .join(Location, Location.id == StockBalance.location_id)
        .with_hint(StockBalance, LOCK_ROW, "mssql")
        .where(
            StockBalance.tenant_id == tenant_id,
            StockBalance.item_id == item_id,
            StockBalance.qty_on_hand > StockBalance.qty_allocated,
            location_filter,
            Location.is_active == true(),
            Location.is_locked == false(),
            Location.is_deleted == false(),
            Location.id.not_in(counting),
            or_(StockBalance.expiry_date.is_(None), StockBalance.expiry_date >= today),
        )
        .order_by(
            case((StockBalance.expiry_date.is_(None), 1), else_=0),
            StockBalance.expiry_date,
            Location.is_pickable.desc(),
            StockBalance.created_at,
            Location.code,
        )
        .execution_options(populate_existing=True)
    )
    return list(db.scalars(stmt).unique())


def balances_at_locations(
    db: Session, tenant_id: uuid.UUID, location_ids: list[uuid.UUID]
) -> list[StockBalance]:
    if not location_ids:
        return []
    return list(
        db.scalars(
            select(StockBalance).where(
                StockBalance.tenant_id == tenant_id, StockBalance.location_id.in_(location_ids)
            )
        ).unique()
    )


def apply_movements(
    db: Session, tenant_id: uuid.UUID, movements: list[Movement], user_id: uuid.UUID
) -> None:
    """Write ledger entries and update balances in the current transaction. If any line is short the error rolls back the whole transaction."""
    occurred_at = utcnow()
    # Lock in a fixed order so two transactions never lock the same balances in opposite order (deadlock)
    for m in sorted(movements, key=_lock_key):
        balance = db.scalars(
            select(StockBalance)
            .with_hint(StockBalance, LOCK_RANGE, "mssql")
            .where(
                StockBalance.tenant_id == tenant_id,
                StockBalance.item_id == m.item_id,
                StockBalance.location_id == m.location_id,
                StockBalance.batch_no == m.batch_no,
                StockBalance.expiry_date == m.expiry_date,
            )
            .execution_options(populate_existing=True)
        ).first()

        current = balance.qty_on_hand if balance else Decimal(0)
        allocated = balance.qty_allocated if balance else Decimal(0)
        new_qty = current + m.qty_change
        new_allocated = allocated + m.allocated_change
        if new_qty < 0 or new_allocated < 0 or new_qty < new_allocated:
            item = db.get(Item, m.item_id)
            location = db.get(Location, m.location_id)
            batch = f" batch {m.batch_no}" if m.batch_no else ""
            reserved = f" (of which {allocated.normalize()} is allocated to orders)" if allocated > 0 else ""
            raise DomainError(
                f"Insufficient stock: item {item.sku_code}{batch} at location {location.code} "
                f"has {current.normalize()}{reserved}, needs {(-m.qty_change).normalize()}"
            )

        if balance is None:
            db.add(
                StockBalance(
                    tenant_id=tenant_id,
                    item_id=m.item_id,
                    location_id=m.location_id,
                    batch_no=m.batch_no,
                    expiry_date=m.expiry_date,
                    qty_on_hand=new_qty,
                    qty_allocated=new_allocated,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        elif new_qty == 0 and new_allocated == 0:
            db.delete(balance)
        else:
            balance.qty_on_hand = new_qty
            balance.qty_allocated = new_allocated
            balance.updated_by = user_id
            balance.row_version += 1

        # Changes to allocation only (releasing a cancelled pick, picking 0) write no ledger entry
        if m.qty_change != 0:
            db.add(
                StockLedger(
                    tenant_id=tenant_id,
                    item_id=m.item_id,
                    location_id=m.location_id,
                    batch_no=m.batch_no,
                    expiry_date=m.expiry_date,
                    qty_change=m.qty_change,
                    movement_type=m.movement_type,
                    ref_document_line_id=m.ref_line_id,
                    occurred_at=occurred_at,
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        # SessionLocal has autoflush off; flush now so later lines hitting the same balance in this document can find it
        db.flush()


def list_balances(
    db: Session,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[StockBalance]:
    stmt = select(StockBalance).where(StockBalance.tenant_id == tenant_id)
    if item_id:
        stmt = stmt.where(StockBalance.item_id == item_id)
    if location_id:
        stmt = stmt.where(StockBalance.location_id == location_id)
    stmt = stmt.order_by(StockBalance.created_at, StockBalance.id).offset(skip).limit(limit)
    return list(db.scalars(stmt).unique())


def list_ledger(
    db: Session,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[StockLedger]:
    stmt = (
        select(StockLedger)
        .options(joinedload(StockLedger.ref_line).joinedload(DocumentLine.document))
        .where(StockLedger.tenant_id == tenant_id)
    )
    if item_id:
        stmt = stmt.where(StockLedger.item_id == item_id)
    if location_id:
        stmt = stmt.where(StockLedger.location_id == location_id)
    stmt = stmt.order_by(StockLedger.occurred_at.desc(), StockLedger.id).offset(skip).limit(limit)
    return list(db.scalars(stmt).unique())
