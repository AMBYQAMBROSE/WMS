import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Numeric, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin


class Uom(Base, TenantScopedMixin):
    __tablename__ = "uom"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(Unicode(20), nullable=False)  # EA / CTN / PLT ...
    name: Mapped[str] = mapped_column(Unicode(50), nullable=False)


class Item(Base, TenantScopedMixin):
    __tablename__ = "item"
    __table_args__ = (UniqueConstraint("tenant_id", "sku_code"),)

    sku_code: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    barcode: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    category: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    base_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    is_batch_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_expiry_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_serial_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    base_uom: Mapped[Uom] = relationship(foreign_keys=[base_uom_id], lazy="joined")
    # Packing units (carton, pallet...): conversions to the base unit, smallest first. Read-only here; ItemService keeps them
    packings: Mapped[list["ItemUomConversion"]] = relationship(
        primaryjoin="and_(Item.id == ItemUomConversion.item_id, ItemUomConversion.to_uom_id == Item.base_uom_id,"
        " ItemUomConversion.is_deleted == False)",
        order_by="ItemUomConversion.factor",
        viewonly=True,
        lazy="selectin",
    )


class ItemBarcode(Base, TenantScopedMixin):
    """Multiple barcodes per item: one SKU may have different barcodes per packing unit (carton/unit barcode)."""

    __tablename__ = "item_barcode"
    __table_args__ = (UniqueConstraint("tenant_id", "barcode"),)

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    barcode: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)


class ItemUomConversion(Base, TenantScopedMixin):
    """Unit conversion, e.g. 1 CTN = 12 EA."""

    __tablename__ = "item_uom_conversion"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    from_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    to_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    from_uom: Mapped[Uom] = relationship(foreign_keys=[from_uom_id], lazy="joined")
