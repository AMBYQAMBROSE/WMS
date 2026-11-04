import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin

LOCATION_TYPES = ("WAREHOUSE", "ZONE", "AISLE", "RACK", "BIN", "DOCK")
# Only these two location types actually hold stock; DOCK is the receiving/shipping staging area
STOCK_LOCATION_TYPES = ("BIN", "DOCK")


class Location(Base, TenantScopedMixin):
    """Location structure as a self-referencing tree: WAREHOUSE > ZONE > AISLE > RACK > BIN/DOCK, replacing Ninso's BinNum/Rack/BinType."""

    __tablename__ = "location"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    location_type: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("location.id"), nullable=True
    )
    path: Mapped[str] = mapped_column(Unicode(400), nullable=False)
    is_pickable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capacity_qty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
