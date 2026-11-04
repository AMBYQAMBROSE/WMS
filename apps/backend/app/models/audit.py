"""Field-level audit log: who changed which record, when, and every changed field's old and new value.

Written automatically for every flush (see _write_audit_log below), so business code does not call anything.
Rows go in with a Core insert on the flush's own connection: same transaction as the change itself, so a rolled-back
request leaves no audit row, and a committed change always has one.

Not covered automatically (ORM events never see them): bulk update()/delete() statements. Services that use one on
an audited table record the change themselves with record_change(); today that is role permissions and user roles.
"""

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Unicode, UnicodeText, Uuid, event, insert, inspect
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.request_context import current_context
from app.models.base import Base
from app.models.business_partner import BusinessPartner
from app.models.document import CountEntry, DocNumberRule, DocumentHeader, DocumentLine, ShipmentInfo
from app.models.integration import IntegrationConnector
from app.models.item import Item, ItemBarcode, ItemUomConversion, Uom
from app.models.location import Location
from app.models.reason_code import ReasonCode
from app.models.returnable_asset import ReturnableAssetTxn, ReturnableAssetType
from app.models.tenant import Tenant, TenantFeatureFlag
from app.models.user import Role, User

ACTION_CREATE = "CREATE"
ACTION_UPDATE = "UPDATE"
ACTION_DELETE = "DELETE"

MASKED = "***"


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_time", "tenant_id", "occurred_at"),
        Index("ix_audit_log_entity", "tenant_id", "entity_id"),
        Index("ix_audit_log_parent", "tenant_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # Null user: the system (background worker, scripts)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    username: Mapped[str | None] = mapped_column(Unicode(100), nullable=True)
    request_id: Mapped[str | None] = mapped_column(Unicode(32), nullable=True)
    action: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    entity_type: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    # Human-readable key at the time of the change (SKU, document number, ...), so the log reads well even after deletes
    entity_label: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    # Owning document for lines, shipment details and count entries: a document's history includes its children
    parent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # JSON object {field: [old, new]}
    changes: Mapped[str] = mapped_column(UnicodeText, nullable=False)


# Audited models: entity type -> (label fields, how to find the owning document). Anything not listed is not audited:
# stock balances and the stock ledger (the ledger is itself the movement history), integration events/jobs/logs
# (they have their own delivery log), document-location freezes, and the log itself.
_AUDITED: dict[type, tuple[str, tuple[str, ...]]] = {
    Tenant: ("tenant", ("code",)),
    TenantFeatureFlag: ("feature_flag", ("feature_code",)),
    User: ("user", ("username",)),
    Role: ("role", ("code",)),
    BusinessPartner: ("business_partner", ("code",)),
    Item: ("item", ("sku_code",)),
    ItemBarcode: ("item_barcode", ("barcode",)),
    ItemUomConversion: ("item_uom_conversion", ()),
    Uom: ("uom", ("code",)),
    Location: ("location", ("code",)),
    ReasonCode: ("reason_code", ("category", "code")),
    ReturnableAssetType: ("returnable_asset_type", ("code",)),
    ReturnableAssetTxn: ("returnable_asset_txn", ("txn_type",)),
    DocNumberRule: ("doc_number_rule", ("doc_type",)),
    IntegrationConnector: ("integration_connector", ("code",)),
    DocumentHeader: ("document", ("doc_type", "doc_no")),
    DocumentLine: ("document_line", ("line_no",)),
    ShipmentInfo: ("shipment_info", ()),
    CountEntry: ("count_entry", ("round",)),
}

# Bookkeeping columns: they change on every write and say nothing the log row itself does not
_IGNORED = {"id", "tenant_id", "created_at", "created_by", "updated_at", "updated_by", "row_version", "last_login_at",
            # Document numbering counters move with every new document; rule changes (prefix, pattern) are still recorded
            "current_period", "current_seq"}
# Recorded as changed, never with their values
_SECRETS = {"password_hash", "secret", "extra_headers"}


def _json_value(value):
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _value(key: str, value):
    return MASKED if key in _SECRETS and value is not None else _json_value(value)


def _label(session: Session, obj, fields: tuple[str, ...]) -> str | None:
    # Children name their document, so they read well in the tenant-wide log: "PO20261104-0001 line 2"
    if isinstance(obj, DocumentLine):
        header = session.get(DocumentHeader, obj.document_id)
        return f"{header.doc_no} line {obj.line_no}" if header else f"Line {obj.line_no}"
    if isinstance(obj, CountEntry):
        line = session.get(DocumentLine, obj.line_id)
        header = session.get(DocumentHeader, line.document_id) if line else None
        return f"{header.doc_no} line {line.line_no} count round {obj.round}" if header else f"Count round {obj.round}"
    parts = [str(getattr(obj, f)) for f in fields if getattr(obj, f, None) is not None]
    return " ".join(parts) or None


def _parent_id(session: Session, obj) -> uuid.UUID | None:
    if isinstance(obj, DocumentLine | ShipmentInfo):
        return obj.document_id
    if isinstance(obj, CountEntry):
        line = session.get(DocumentLine, obj.line_id)
        return line.document_id if line else None
    return None


def _tenant_id(session: Session, obj) -> uuid.UUID | None:
    if isinstance(obj, Tenant):
        return obj.id
    if isinstance(obj, ShipmentInfo):
        header = session.get(DocumentHeader, obj.document_id)
        return header.tenant_id if header else current_context().tenant_id
    return getattr(obj, "tenant_id", None) or current_context().tenant_id


def _changes(obj, action: str) -> dict[str, list]:
    state = inspect(obj)
    changes: dict[str, list] = {}
    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in _IGNORED:
            continue
        if action == ACTION_CREATE:
            value = state.dict.get(key)
            if value is not None and not (key == "is_deleted" and value is False):
                changes[key] = [None, _value(key, value)]
        elif action == ACTION_DELETE and state.deleted:
            value = state.dict.get(key)
            if value is not None and key != "is_deleted":
                changes[key] = [_value(key, value), None]
        else:
            history = state.attrs[key].history
            if not history.has_changes():
                continue
            old = history.deleted[0] if history.deleted else None
            new = history.added[0] if history.added else None
            if old != new:
                changes[key] = [_value(key, old), _value(key, new)]
    return changes


def _row(session: Session, obj, entity_type: str, label_fields, action: str, changes: dict) -> dict:
    context = current_context()
    user_id = context.user_id or getattr(obj, "updated_by", None)
    return {
        "id": uuid.uuid4(),
        "tenant_id": _tenant_id(session, obj),
        "occurred_at": datetime.now(UTC).replace(tzinfo=None),
        "user_id": user_id,
        "username": context.username if context.user_id else None,
        "request_id": context.request_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": obj.document_id if isinstance(obj, ShipmentInfo) else obj.id,
        "entity_label": _label(session, obj, label_fields),
        "parent_id": _parent_id(session, obj),
        "changes": json.dumps(changes, ensure_ascii=False),
    }


def record_change(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    entity_label: str | None,
    changes: dict[str, list],
    action: str = ACTION_UPDATE,
) -> None:
    """Explicit audit row for changes the flush hook cannot see (bulk statements); no-op without changes"""
    if not changes:
        return
    context = current_context()
    session.connection().execute(
        insert(AuditLog.__table__),
        [{
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "occurred_at": datetime.now(UTC).replace(tzinfo=None),
            "user_id": context.user_id,
            "username": context.username,
            "request_id": context.request_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "entity_label": entity_label,
            "parent_id": None,
            "changes": json.dumps(changes, ensure_ascii=False),
        }],
    )


@event.listens_for(Session, "after_flush")
def _write_audit_log(session: Session, _flush_context) -> None:
    """In after_flush the new/dirty/deleted sets and attribute history still describe what was just written,
    and primary keys and relationship-synced foreign keys are filled in"""
    rows = []
    for objects, default_action in (
        (session.new, ACTION_CREATE), (session.dirty, ACTION_UPDATE), (session.deleted, ACTION_DELETE),
    ):
        for obj in objects:
            spec = _AUDITED.get(type(obj))
            if spec is None:
                continue
            action = default_action
            if action == ACTION_UPDATE:
                deleted = inspect(obj).attrs.is_deleted.history if hasattr(obj, "is_deleted") else None
                if deleted is not None and deleted.added and deleted.added[0] is True:
                    action = ACTION_DELETE  # soft delete
            changes = _changes(obj, action)
            if action == ACTION_UPDATE and not changes:
                continue
            entity_type, label_fields = spec
            row = _row(session, obj, entity_type, label_fields, action, changes)
            if row["tenant_id"] is not None:
                rows.append(row)
    if rows:
        session.connection().execute(insert(AuditLog.__table__), rows)
