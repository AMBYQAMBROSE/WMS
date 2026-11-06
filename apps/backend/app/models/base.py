import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Uuid, event, inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuditMixin:
    """Common audit fields present on every business table. The Tenant table itself only uses this mixin (it belongs to no tenant)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow, nullable=False
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TenantScopedMixin(AuditMixin):
    """Inherited by every business table except Tenant and Permission (system-wide); adds the tenant_id isolation column."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("tenant.id"), index=True, nullable=False
    )


# Fields that do not by themselves make a new version of a record
_NOT_A_CHANGE = {"row_version", "updated_at"}


@event.listens_for(Session, "before_flush")
def _bump_row_version(session: Session, _flush_context, _instances) -> None:
    """Every change to an audited record bumps its row_version, so optimistic locking (check_version) sees every write,
    whichever code path made it. Code that already bumped it in this flush (to mark a document changed when only its
    lines changed) is left alone."""
    for obj in session.dirty:
        if not isinstance(obj, AuditMixin):
            continue
        state = inspect(obj)
        if state.attrs.row_version.history.has_changes():
            continue
        if any(
            state.attrs[attr.key].history.has_changes()
            for attr in state.mapper.column_attrs
            if attr.key not in _NOT_A_CHANGE
        ):
            obj.row_version = (obj.row_version or 0) + 1
