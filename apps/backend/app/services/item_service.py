import uuid
from decimal import Decimal

from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError
from app.core.formatting import qty_text
from app.core.gs1 import parse as parse_gs1
from app.models.document import DocumentHeader, DocumentLine
from app.models.item import Item, ItemBarcode, ItemUomConversion
from app.repositories.base import BaseRepository, check_version
from app.schemas.item import ItemCreate, ItemPackingIn, ItemUpdate
from app.services.document_common import get_uom
from app.services.master_guard import delete_item


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
            **data.model_dump(exclude={"packings"}),
        )
        self.repo.create(item)
        self._set_packings(item, data.packings, created_by)
        return item

    def update(self, item: Item, data: ItemUpdate, updated_by: uuid.UUID) -> Item:
        check_version(item, data.row_version, f"Item {item.sku_code}")
        fields = data.model_dump(exclude_unset=True, exclude={"row_version", "packings"})
        fields["updated_by"] = updated_by
        self.repo.update(item, fields)
        if data.packings is not None:
            self._set_packings(item, data.packings, updated_by)
        return item

    def _set_packings(self, item: Item, packings: list[ItemPackingIn], user_id: uuid.UUID) -> None:
        """Make the item's packing units (conversions to its base unit) exactly `packings`.

        Documents keep their quantities in the unit they were entered in and convert with the item's current factor, so a
        factor that documents already use cannot change or go away: that would silently change what those documents mean."""
        db, t = self.repo.db, item.tenant_id
        wanted: dict[uuid.UUID, Decimal] = {}
        for p in packings:
            uom = get_uom(db, t, p.uom_id)
            if p.uom_id == item.base_uom_id:
                raise DomainError(f"{uom.code} is the base unit of item {item.sku_code}; it needs no conversion")
            if p.uom_id in wanted:
                raise DomainError(f"Unit {uom.code} is listed twice for item {item.sku_code}")
            wanted[p.uom_id] = p.factor

        current = {
            c.from_uom_id: c
            for c in db.scalars(
                select(ItemUomConversion).where(
                    ItemUomConversion.tenant_id == t,
                    ItemUomConversion.item_id == item.id,
                    ItemUomConversion.to_uom_id == item.base_uom_id,
                    ItemUomConversion.is_deleted == false(),
                )
            )
        }
        changed = [c for uom_id, c in current.items() if wanted.get(uom_id) != c.factor]
        for conversion in changed:
            docs = list(
                db.scalars(
                    select(DocumentHeader.doc_no)
                    .join(DocumentLine, DocumentLine.document_id == DocumentHeader.id)
                    .where(
                        DocumentLine.tenant_id == t,
                        DocumentLine.item_id == item.id,
                        DocumentLine.uom_id == conversion.from_uom_id,
                    )
                    .distinct()
                    .order_by(DocumentHeader.doc_no)
                    .limit(3)
                )
            )
            if docs:
                code = conversion.from_uom.code
                more = " and others" if len(docs) == 3 else ""
                raise ConflictError(
                    f"{code} of item {item.sku_code} is used by documents ({', '.join(docs)}{more}), so its quantity "
                    f"({qty_text(conversion.factor)} per {code}) cannot be changed or removed"
                )

        for uom_id, conversion in current.items():
            if uom_id not in wanted:
                db.delete(conversion)
            elif wanted[uom_id] != conversion.factor:
                conversion.factor = wanted[uom_id]
                conversion.updated_by = user_id
        for uom_id, factor in wanted.items():
            if uom_id not in current:
                db.add(
                    ItemUomConversion(
                        tenant_id=t,
                        item_id=item.id,
                        from_uom_id=uom_id,
                        to_uom_id=item.base_uom_id,
                        factor=factor,
                        created_by=user_id,
                        updated_by=user_id,
                    )
                )
        db.flush()
        db.expire(item, ["packings"])

    def delete(self, item: Item) -> None:
        delete_item(self.repo.db, item)
