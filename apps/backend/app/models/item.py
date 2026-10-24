import uuid

from sqlalchemy import Boolean, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class Uom(Base, TenantScopedMixin):
    __tablename__ = "uom"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(20), nullable=False)  # EA / CTN / PLT ...
    name: Mapped[str] = mapped_column(String(50), nullable=False)


class Item(Base, TenantScopedMixin):
    __tablename__ = "item"
    __table_args__ = (UniqueConstraint("tenant_id", "sku_code"),)

    sku_code: Mapped[str] = mapped_column(String(50), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    base_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    is_batch_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_expiry_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_serial_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ItemBarcode(Base, TenantScopedMixin):
    """一品多码：同一个 SKU 在不同包装单位下可能有不同条码（整箱码/单件码）。"""

    __tablename__ = "item_barcode"
    __table_args__ = (UniqueConstraint("tenant_id", "barcode"),)

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    barcode: Mapped[str] = mapped_column(String(50), nullable=False)
    uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)


class ItemUomConversion(Base, TenantScopedMixin):
    """单位换算，如 1 CTN = 12 EA。"""

    __tablename__ = "item_uom_conversion"

    item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("item.id"), nullable=False)
    from_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    to_uom_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("uom.id"), nullable=False)
    factor: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False)
