import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin
from app.models.document import DocumentLine
from app.models.item import Item
from app.models.location import Location


class StockLedger(Base, TenantScopedMixin):
    """Stock ledger: the only entry point for stock changes, append-only. Quantities are always base units."""

    __tablename__ = "stock_ledger"
    # Reports scan the ledger by time range (in/out trend, turnover, partner ledger)
    __table_args__ = (
        Index("ix_stock_ledger_tenant_time", "tenant_id", "occurred_at"),
        # Deleting a location makes SQL Server check the ledger for references
        Index("ix_stock_ledger_location", "location_id"),
    )

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
    """Current stock balance, updated in the same transaction as the ledger.
    SQL Server unique constraints treat NULLs as equal, so stock without a batch has a single row per (item, location).
    """

    __tablename__ = "stock_balance"
    __table_args__ = (
        UniqueConstraint("tenant_id", "item_id", "location_id", "batch_no", "expiry_date"),
        # PDA scans a location to look up stock
        Index("ix_stock_balance_location", "location_id"),
    )

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("location.id"), nullable=False)
    batch_no: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    qty_on_hand: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal(0), nullable=False)
    # Reserved for outbound orders: allocated in a bin but not yet picked, or picked and waiting in staging to ship.
    # available = qty_on_hand - qty_allocated, and always qty_on_hand >= qty_allocated
    qty_allocated: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal(0), server_default="0", nullable=False
    )

    item: Mapped[Item] = relationship(lazy="joined")
    location: Mapped[Location] = relationship(lazy="joined")
