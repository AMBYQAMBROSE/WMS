from sqlalchemy import Boolean, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin


class BusinessPartner(Base, TenantScopedMixin):
    """Merges Ninso's Outlet (customer/store) and Supplier; partner_type tells the roles apart."""

    __tablename__ = "business_partner"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    partner_type: Mapped[str] = mapped_column(Unicode(20), nullable=False)  # customer/supplier/both
    contact_name: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
