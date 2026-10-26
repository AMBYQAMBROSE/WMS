import uuid
from typing import Generic, TypeVar

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """通用的租户隔离 CRUD 仓储，business_partner/item/location 等主数据表共用。

    入库/出库等单据的专属查询逻辑在对应 Phase 再写 Service 层方法，不在这里预先猜测。
    """

    def __init__(self, db: Session, model: type[ModelType]):
        self.db = db
        self.model = model

    def _base_query(self, tenant_id: uuid.UUID):
        return select(self.model).where(
            self.model.tenant_id == tenant_id,
            # SQL Server 不支持 "IS 0"，所以不用 .is_(False)
            self.model.is_deleted == false(),
        )

    def get(self, tenant_id: uuid.UUID, id: uuid.UUID) -> ModelType | None:
        return self.db.scalars(self._base_query(tenant_id).where(self.model.id == id)).first()

    def list(self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[ModelType]:
        # SQL Server 分页(OFFSET)必须带 ORDER BY
        stmt = (
            self._base_query(tenant_id)
            .order_by(self.model.created_at, self.model.id)
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
