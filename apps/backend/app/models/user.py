import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Unicode, UnicodeText, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScopedMixin


class User(Base, TenantScopedMixin):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("tenant_id", "username"),)

    username: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    display_name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    email: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    # Nullable: leaves room for AD/SSO users without a local password. auth_provider marks the login method; only "local" is implemented.
    password_hash: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    auth_provider: Mapped[str] = mapped_column(Unicode(20), default="local", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Read-only: roles are changed through the user_role table, see UserService.set_roles
    roles: Mapped[list["Role"]] = relationship(secondary="user_role", lazy="selectin", viewonly=True)


class Role(Base, TenantScopedMixin):
    __tablename__ = "role"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Permission(Base):
    """The permission list is system-wide, not per tenant; maintained by code/migrations, no create/delete API."""

    __tablename__ = "permission"

    code: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    module: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    description: Mapped[str] = mapped_column(Unicode(200), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permission"

    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("role.id"), primary_key=True)
    permission_code: Mapped[str] = mapped_column(
        ForeignKey("permission.code"), primary_key=True
    )


class UserRole(Base):
    __tablename__ = "user_role"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("role.id"), primary_key=True)


class UserPreference(Base):
    """Per-user UI settings (saved list views, visible columns, ...), stored on the server because warehouse PCs are
    often shared: browser storage would mix users and not follow them to another PC. The value is JSON owned by the
    web app; the backend only stores it. Not audited: personal display settings, not business data."""

    __tablename__ = "user_preference"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), primary_key=True)
    key: Mapped[str] = mapped_column(Unicode(100), primary_key=True)
    value: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
