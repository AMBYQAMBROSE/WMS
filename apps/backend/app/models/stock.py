import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin
from app.models.document import DocumentLine
from app.models.item import Item
from app.models.location import Location


class StockLedger(Base, TenantScopedMixin):
    """库存流水：所有库存增减的唯一入口，只增不改。数量一律为基本单位。"""

    __tablename__ = "stock_ledger"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), index=True, nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location.id"), nullable=False)
    batch_no: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    qty_change: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    movement_type: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    ref_document_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_line.id"), nullable=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    item: Mapped[Item] = relationship(lazy="joined")
    location: Mapped[Location] = relationship(lazy="joined")
    ref_line: Mapped[DocumentLine | None] = relationship()


class StockBalance(Base, TenantScopedMixin):
    """当前库存余额，与流水在同一事务内同步更新。
    SQL Server 唯一约束把 NULL 视为相等，所以无批次的库存每个 (商品, 仓位) 只会有一行。
    """

    __tablename__ = "stock_balance"
    __table_args__ = (
        UniqueConstraint("tenant_id", "item_id", "location_id", "batch_no", "expiry_date"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location.id"), nullable=False)
    batch_no: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    qty_on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0), nullable=False)

    item: Mapped[Item] = relationship(lazy="joined")
    location: Mapped[Location] = relationship(lazy="joined")
