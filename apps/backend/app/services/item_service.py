import uuid

from sqlalchemy.orm import Session

from app.models.item import Item
from app.repositories.base import BaseRepository
from app.schemas.item import ItemCreate, ItemUpdate


class ItemService:
    def __init__(self, db: Session):
        self.repo = BaseRepository(db, Item)

    def list(self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[Item]:
        return self.repo.list(tenant_id, skip, limit)

    def get(self, tenant_id: uuid.UUID, id: uuid.UUID) -> Item | None:
        return self.repo.get(tenant_id, id)

    def create(self, tenant_id: uuid.UUID, data: ItemCreate, created_by: uuid.UUID) -> Item:
        item = Item(
            tenant_id=tenant_id,
            created_by=created_by,
            updated_by=created_by,
            **data.model_dump(),
        )
        return self.repo.create(item)

    def update(self, item: Item, data: ItemUpdate, updated_by: uuid.UUID) -> Item:
        fields = data.model_dump(exclude_unset=True)
        fields["updated_by"] = updated_by
        return self.repo.update(item, fields)

    def delete(self, item: Item) -> None:
        self.repo.soft_delete(item)
