from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import AuditMixin, Base, TenantScopedMixin


class Tenant(Base, AuditMixin):
    __tablename__ = "tenant"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    default_locale: Mapped[str] = mapped_column(String(10), default="zh-CN", nullable=False)
    default_timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Shanghai", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TenantFeatureFlag(Base, TenantScopedMixin):
    __tablename__ = "tenant_feature_flag"
    __table_args__ = (UniqueConstraint("tenant_id", "feature_code"),)

    feature_code: Mapped[str] = mapped_column(String(100), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
