import uuid

from sqlalchemy import or_, select, true
from sqlalchemy.orm import Session

from app.core.gs1 import parse as parse_gs1
from app.models.item import Item, ItemBarcode
from app.repositories.base import BaseRepository, check_version
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.master_guard import check_item_deletable


class ItemService:
    def __init__(self, db: Session):
        self.repo = BaseRepository(db, Item)

    def list(
        self,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        keyword: str | None = None,
        ids: list[uuid.UUID] | None = None,
        active_only: bool = False,
    ) -> list[Item]:
        """keyword: SKU / name contains, or exact barcode match (incl. extra barcodes); ids: fetch by ID (to display selected dropdown values)"""
        conditions = []
        if keyword := (keyword or "").strip():
            # A scanned GS1 carton code or stock label: look for the item it names (GTIN / AI 240), not the whole text
            gs1 = parse_gs1(keyword)
            codes = gs1.item_keys() if gs1 else [keyword]
            conditions.append(
                or_(
                    Item.sku_code.contains(keyword, autoescape=True),
                    Item.name.contains(keyword, autoescape=True),
                    Item.barcode.in_(codes),
                    Item.sku_code.in_(codes),
                    Item.id.in_(select(ItemBarcode.item_id).where(ItemBarcode.tenant_id == tenant_id, ItemBarcode.barcode.in_(codes))),
                )
            )
        if ids:
            conditions.append(Item.id.in_(ids))
        if active_only:
            conditions.append(Item.is_active == true())
        return self.repo.list(tenant_id, skip, limit, *conditions)

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
        check_version(item, data.row_version, f"Item {item.sku_code}")
        fields = data.model_dump(exclude_unset=True, exclude={"row_version"})
        fields["updated_by"] = updated_by
        return self.repo.update(item, fields)

    def delete(self, item: Item) -> None:
        check_item_deletable(self.repo.db, item.tenant_id, item.id, item.sku_code)
        self.repo.soft_delete(item)
