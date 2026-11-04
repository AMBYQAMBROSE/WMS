from sqlalchemy import Boolean, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScopedMixin

REASON_CATEGORY_ADJUST = "ADJUST"
REASON_CATEGORY_RETURN = "RETURN"


class ReasonCode(Base, TenantScopedMixin):
    """Business reason codes (adjustment reasons, return reasons, ...); category tells their use apart."""

    __tablename__ = "reason_code"
    __table_args__ = (UniqueConstraint("tenant_id", "category", "code"),)

    category: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    code: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    # Transaction code in an external ERP (Ninso AdjTransCode); empty when there is no integration
    external_code: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
