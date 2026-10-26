import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import false, select
from sqlalchemy.orm import Session, joinedload

from app.core.errors import DomainError
from app.models.document import DocumentLine
from app.models.item import Item, ItemUomConversion
from app.models.location import Location
from app.models.stock import StockBalance, StockLedger
from app.services.document_common import LOCK_RANGE, utcnow

MOVE_RECEIVE = "RECEIVE"
MOVE_PUTAWAY_OUT = "PUTAWAY_OUT"
MOVE_PUTAWAY_IN = "PUTAWAY_IN"


@dataclass(frozen=True)
class Movement:
    item_id: uuid.UUID
    location_id: uuid.UUID
    batch_no: str | None
    expiry_date: date | None
    qty_change: Decimal
    movement_type: str
    ref_line_id: uuid.UUID | None


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
        raise DomainError(f"商品 {item.sku_code} 未配置该单位到基本单位的换算")
    return qty * conversion.factor


def _lock_key(m: Movement) -> tuple:
    return (str(m.item_id), str(m.location_id), m.batch_no or "", str(m.expiry_date or ""))


def apply_movements(
    db: Session, tenant_id: uuid.UUID, movements: list[Movement], user_id: uuid.UUID
) -> None:
    """在当前事务内写流水并更新余额。任一行库存不足则抛错，整个事务回滚。"""
    occurred_at = utcnow()
    # 按固定顺序加锁，避免两个事务交叉锁同一批余额行导致死锁
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
        new_qty = current + m.qty_change
        if new_qty < 0:
            item = db.get(Item, m.item_id)
            location = db.get(Location, m.location_id)
            batch = f" 批次 {m.batch_no}" if m.batch_no else ""
            raise DomainError(
                f"库存不足：商品 {item.sku_code}{batch} 在仓位 {location.code} "
                f"现有 {current.normalize()}，需要 {(-m.qty_change).normalize()}"
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
                    created_by=user_id,
                    updated_by=user_id,
                )
            )
        elif new_qty == 0:
            db.delete(balance)
        else:
            balance.qty_on_hand = new_qty
            balance.updated_by = user_id
            balance.row_version += 1

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
        # SessionLocal 关闭了 autoflush，同一单据内多行命中同一余额时必须先落库才能查到
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
