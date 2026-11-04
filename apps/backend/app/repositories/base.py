import uuid
from typing import Generic, TypeVar

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic tenant-isolated CRUD repository shared by master data tables such as business_partner/item/location.

    Document-specific queries (inbound/outbound) belong in service methods, not guessed up front here.
    """

    def __init__(self, db: Session, model: type[ModelType]):
        self.db = db
        self.model = model

    def _base_query(self, tenant_id: uuid.UUID):
        return select(self.model).where(
            self.model.tenant_id == tenant_id,
            # SQL Server does not support "IS 0", so .is_(False) is not used
            self.model.is_deleted == false(),
        )

    def get(self, tenant_id: uuid.UUID, id: uuid.UUID) -> ModelType | None:
        return self.db.scalars(self._base_query(tenant_id).where(self.model.id == id)).first()

    def list(self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50, *conditions) -> list[ModelType]:
        # SQL Server paging (OFFSET) requires ORDER BY; newest first, so a just-created record shows on the first page
        stmt = (
            self._base_query(tenant_id)
            .where(*conditions)
            .order_by(self.model.created_at.desc(), self.model.id)
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def create(self, obj: ModelType) -> ModelType:
        self.db.add(obj)
        self.db.flush()
        return obj

    def update(self, obj: ModelType, fields: dict) -> ModelType:
        for key, value in fields.items():
            setattr(obj, key, value)
        obj.row_version += 1
        self.db.flush()
        return obj

    def soft_delete(self, obj: ModelType) -> None:
        obj.is_deleted = True
        self.db.flush()
