import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin
from app.models.business_partner import BusinessPartner


class ReturnableAssetType(Base, TenantScopedMixin):
    """Returnable asset type: pallets, crates, roll cages, etc. (Ninso Tool). Tracks quantities only, not individual asset numbers."""

    __tablename__ = "returnable_asset_type"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ReturnableAssetTxn(Base, TenantScopedMixin):
    """Returnable asset ledger (append-only): lending to a partner is positive, returns negative; outstanding per partner and type = ledger total."""

    __tablename__ = "returnable_asset_txn"

    partner_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business_partner.id"), index=True, nullable=False
    )
    asset_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("returnable_asset_type.id"), nullable=False
    )
    txn_type: Mapped[str] = mapped_column(Unicode(20), nullable=False)  # ISSUE / RETURN
    qty_change: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    # Optional linked document (e.g. a shipment) to trace which truckload the crates went out with
    ref_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_header.id"), nullable=True
    )
    remark: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    partner: Mapped[BusinessPartner] = relationship(lazy="joined")
    asset_type: Mapped[ReturnableAssetType] = relationship(lazy="joined")
