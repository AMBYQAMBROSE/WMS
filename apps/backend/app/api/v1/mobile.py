import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.models.item import Item, ItemBarcode, ItemUomConversion, Uom
from app.models.location import STOCK_LOCATION_TYPES, Location
from app.schemas.document import Qty
from app.services.document_common import utcnow

router = APIRouter(route_class=TransactionalRoute, prefix="/mobile", tags=["mobile"])


class _Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class MobileItem(_Orm):
    id: uuid.UUID
    sku_code: str
    name: str
    barcode: str | None
    base_uom_id: uuid.UUID
    is_batch_managed: bool
    is_expiry_managed: bool


class MobileBarcode(_Orm):
    barcode: str
    item_id: uuid.UUID
    uom_id: uuid.UUID


class MobileUom(_Orm):
    id: uuid.UUID
    code: str
    name: str


class MobileConversion(_Orm):
    item_id: uuid.UUID
    from_uom_id: uuid.UUID
    to_uom_id: uuid.UUID
    factor: Qty


class MobileLocation(_Orm):
    id: uuid.UUID
    code: str
    name: str
    location_type: str
    is_locked: bool


class MasterData(BaseModel):
    generated_at: datetime
    items: list[MobileItem]
    barcodes: list[MobileBarcode]
    uoms: list[MobileUom]
    conversions: list[MobileConversion]
    locations: list[MobileLocation]


def _active(db: Session, model, tenant_id: uuid.UUID, *conditions):
    return list(
        db.scalars(
            select(model).where(model.tenant_id == tenant_id, model.is_deleted == false(), *conditions)
        ).unique()
    )


def _compact(db: Session, tenant_id: uuid.UUID) -> dict:
    """Compact (columnar) format: field names appear once and unit IDs become indexes into the uoms array. About 40% of the default format with 50,000 items.
    Units of measure are few and stay an array of objects; other tables are {"fields": [...], "rows": [[...]]}."""
    uoms = _active(db, Uom, tenant_id)
    uom_index = {u.id: i for i, u in enumerate(uoms)}

    def table(model, columns, *conditions, uom_fields=()):
        names = [c.key for c in columns]
        rows = db.execute(
            select(*columns).where(model.tenant_id == tenant_id, model.is_deleted == false(), *conditions)
        ).all()
        out = []
        for row in rows:
            values = []
            for name, value in zip(names, row, strict=True):
                if name in uom_fields:
                    value = uom_index.get(value)
                elif isinstance(value, uuid.UUID):
                    value = str(value)
                elif isinstance(value, bool):
                    value = int(value)
                elif value is not None and not isinstance(value, (int, str)):
                    value = float(value)
                values.append(value)
            out.append(values)
        return {"fields": names, "rows": out}

    return {
        "format": "compact",
        "generated_at": utcnow().isoformat() + "Z",
        "uoms": [{"id": str(u.id), "code": u.code, "name": u.name} for u in uoms],
        "items": table(
            Item,
            [Item.id, Item.sku_code, Item.name, Item.barcode, Item.base_uom_id, Item.is_batch_managed, Item.is_expiry_managed],
            Item.is_active == true(),
            uom_fields=("base_uom_id",),
        ),
        "barcodes": table(ItemBarcode, [ItemBarcode.barcode, ItemBarcode.item_id, ItemBarcode.uom_id], uom_fields=("uom_id",)),
        "conversions": table(
            ItemUomConversion,
            [ItemUomConversion.item_id, ItemUomConversion.from_uom_id, ItemUomConversion.to_uom_id, ItemUomConversion.factor],
            uom_fields=("from_uom_id", "to_uom_id"),
        ),
        "locations": table(
            Location,
            [Location.id, Location.code, Location.name, Location.location_type, Location.is_locked],
            Location.is_active == true(),
            Location.location_type.in_(STOCK_LOCATION_TYPES),
        ),
    }


@router.get("/master-data", response_model=None)
def get_master_data(
    format: Literal["full", "compact"] = "full",
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("mobile.sync")),
) -> MasterData | dict:
    """format=compact is the compact format used by the current PDA app; the default format is kept for older app versions"""
    if format == "compact":
        return _compact(db, user.tenant_id)
    """The PDA downloads the master data needed to recognize scans in one go and caches it locally, so barcodes and locations are recognized offline too."""
    tenant_id = user.tenant_id
    return MasterData(
        generated_at=utcnow(),
        items=_active(db, Item, tenant_id, Item.is_active == true()),
        barcodes=_active(db, ItemBarcode, tenant_id),
        uoms=_active(db, Uom, tenant_id),
        conversions=_active(db, ItemUomConversion, tenant_id),
        locations=_active(
            db,
            Location,
            tenant_id,
            Location.is_active == true(),
            Location.location_type.in_(STOCK_LOCATION_TYPES),
        ),
    )
