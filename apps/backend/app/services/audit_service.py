import json
import uuid
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.business_partner import BusinessPartner
from app.models.document import DocumentHeader
from app.models.item import Item, Uom
from app.models.location import Location
from app.models.reason_code import ReasonCode
from app.models.returnable_asset import ReturnableAssetType
from app.models.user import User
from app.schemas.audit import AuditChange, AuditLogRead

IN_CHUNK = 1000  # SQL Server allows about 2100 parameters per statement

# Fields holding the id of another record -> (model, column shown instead of the id)
_REFERENCES = {
    "item_id": (Item, Item.sku_code),
    "uom_id": (Uom, Uom.code),
    "base_uom_id": (Uom, Uom.code),
    "from_uom_id": (Uom, Uom.code),
    "to_uom_id": (Uom, Uom.code),
    "location_id": (Location, Location.code),
    "from_location_id": (Location, Location.code),
    "to_location_id": (Location, Location.code),
    "parent_id": (Location, Location.code),  # only locations have a parent
    "partner_id": (BusinessPartner, BusinessPartner.code),
    "reason_code_id": (ReasonCode, ReasonCode.code),
    "asset_type_id": (ReturnableAssetType, ReturnableAssetType.code),
    "ref_document_id": (DocumentHeader, DocumentHeader.doc_no),
    "document_id": (DocumentHeader, DocumentHeader.doc_no),
    "confirmed_by": (User, User.username),
    "counted_by": (User, User.username),
}


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


class AuditService:
    def __init__(self, db: Session, tenant_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id

    def list(
        self,
        *,
        entity_id: uuid.UUID | None = None,
        entity_type: str | None = None,
        user_id: uuid.UUID | None = None,
        action: str | None = None,
        keyword: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[AuditLogRead]:
        stmt = select(AuditLog).where(AuditLog.tenant_id == self.tenant_id)
        if entity_id:
            # A document's history includes its lines, shipment details and count entries
            stmt = stmt.where(or_(AuditLog.entity_id == entity_id, AuditLog.parent_id == entity_id))
        if entity_type:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if keyword:
            stmt = stmt.where(AuditLog.entity_label.contains(keyword.strip(), autoescape=True))
        if occurred_from:
            stmt = stmt.where(AuditLog.occurred_at >= _naive_utc(occurred_from))
        if occurred_to:
            stmt = stmt.where(AuditLog.occurred_at < _naive_utc(occurred_to))
        stmt = stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id).offset(skip).limit(limit)
        return self._read(list(self.db.scalars(stmt)))

    def _read(self, logs: list[AuditLog]) -> list[AuditLogRead]:
        parsed = [(log, json.loads(log.changes)) for log in logs]

        wanted: dict[str, set[uuid.UUID]] = {}
        for log, changes in parsed:
            for field, values in changes.items():
                if field in _REFERENCES:
                    for value in values:
                        if isinstance(value, str):
                            with suppress(ValueError):  # "***" or another non-id value
                                wanted.setdefault(field, set()).add(uuid.UUID(value))
            if log.user_id and not log.username:
                wanted.setdefault("confirmed_by", set()).add(log.user_id)
        names = self._lookup(wanted)

        def show(field: str, value):
            if field in _REFERENCES and isinstance(value, str):
                return names.get((_REFERENCES[field][0], value), value)
            return value

        return [
            AuditLogRead(
                id=log.id,
                occurred_at=log.occurred_at,
                user_id=log.user_id,
                username=log.username or (names.get((User, str(log.user_id))) if log.user_id else None),
                request_id=log.request_id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                entity_label=log.entity_label,
                parent_id=log.parent_id,
                changes=[AuditChange(field=f, old=show(f, old), new=show(f, new)) for f, (old, new) in changes.items()],
            )
            for log, changes in parsed
        ]

    def _lookup(self, wanted: dict[str, set[uuid.UUID]]) -> dict[tuple[type, str], str]:
        """(model, id as string) -> display value, one query per referenced model"""
        ids_by_model: dict[type, tuple[object, set[uuid.UUID]]] = {}
        for field, ids in wanted.items():
            model, column = _REFERENCES[field]
            ids_by_model.setdefault(model, (column, set()))[1].update(ids)
        names: dict[tuple[type, str], str] = {}
        for model, (column, ids) in ids_by_model.items():
            id_list = list(ids)
            for i in range(0, len(id_list), IN_CHUNK):
                for row_id, name in self.db.execute(
                    select(model.id, column).where(model.id.in_(id_list[i:i + IN_CHUNK]))
                ):
                    names[(model, str(row_id))] = name
        return names
