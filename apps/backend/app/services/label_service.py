import json
import uuid
from datetime import UTC
from zoneinfo import ZoneInfo

from sqlalchemy import false, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.formatting import qty_text
from app.models.item import Item
from app.models.label import LabelProfile
from app.models.location import STOCK_LOCATION_TYPES, Location
from app.models.tenant import Tenant
from app.repositories.base import BaseRepository, check_version
from app.schemas.label import (
    ItemLabelRequest,
    LabelLayout,
    LabelProfileIn,
    LabelProfileRead,
    LabelProfileUpdate,
    LocationLabelRequest,
    StockLabelRequest,
)
from app.services.document_common import DOC_GRN, get_document
from app.services.printing import labels as label_pdf
from app.services.printing.labels import LabelContent

MAX_LABELS = 5000


class LabelService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db, self.tenant_id, self.user_id = db, tenant_id, user_id
        self.repo = BaseRepository(db, LabelProfile)

    # ----- profiles -----

    def list_profiles(self, purpose: str | None = None) -> list[LabelProfile]:
        stmt = self.repo._base_query(self.tenant_id).order_by(LabelProfile.purpose, LabelProfile.is_default.desc(), LabelProfile.name)
        if purpose:
            stmt = stmt.where(LabelProfile.purpose == purpose)
        return list(self.db.scalars(stmt))

    def get_profile(self, profile_id: uuid.UUID) -> LabelProfile:
        profile = self.repo.get(self.tenant_id, profile_id)
        if profile is None:
            raise NotFoundError("Label profile not found")
        return profile

    def create_profile(self, data: LabelProfileIn) -> LabelProfile:
        profile = LabelProfile(tenant_id=self.tenant_id, created_by=self.user_id, updated_by=self.user_id, **self._columns(data))
        if data.is_default:
            self._clear_default(data.purpose)
        return self.repo.create(profile)

    def update_profile(self, profile_id: uuid.UUID, data: LabelProfileUpdate) -> LabelProfile:
        profile = self.get_profile(profile_id)
        check_version(profile, data.row_version, f"Label profile {profile.name}")
        if data.is_default:
            self._clear_default(data.purpose, keep=profile.id)
        return self.repo.update(profile, {**self._columns(data), "updated_by": self.user_id})

    def delete_profile(self, profile_id: uuid.UUID) -> None:
        self.repo.soft_delete(self.get_profile(profile_id))

    def _columns(self, data: LabelProfileIn) -> dict:
        fields = data.model_dump(exclude={"row_version"})
        fields["fields"] = json.dumps(data.fields)
        return fields

    def _clear_default(self, purpose: str, keep: uuid.UUID | None = None) -> None:
        # ORM updates (not a bulk update()) so the audit log records the old default losing its flag
        for other in self.list_profiles(purpose):
            if other.is_default and other.id != keep:
                other.is_default = False
                other.updated_by = self.user_id
        self.db.flush()

    def layout(self, purpose: str, profile_id: uuid.UUID | None) -> tuple[LabelLayout, str]:
        """The chosen profile, else the purpose's default profile, else the built-in layout"""
        if profile_id is not None:
            profile = self.get_profile(profile_id)
            if profile.purpose != purpose:
                raise DomainError(f"Label profile {profile.name} is for {profile.purpose.lower()} labels")
        else:
            profile = next((p for p in self.list_profiles(purpose) if p.is_default), None)
        if profile is None:
            return label_pdf.BUILT_IN[purpose], "Built-in"
        return LabelProfileRead.model_validate(profile), profile.name

    # ----- printing -----

    def item_labels(self, data: ItemLabelRequest) -> bytes:
        layout, _ = self.layout("ITEM", data.profile_id)
        items = {
            i.id: i
            for i in self.db.scalars(
                select(Item).where(Item.tenant_id == self.tenant_id, Item.is_deleted == false(), Item.id.in_(data.item_ids))
            )
        }
        missing = [str(i) for i in data.item_ids if i not in items]
        if missing:
            raise NotFoundError(f"Item not found: {', '.join(missing[:5])}")
        self._check_count(len(data.item_ids) * data.copies)
        contents = []
        # Keep the order the user chose, each item's copies together so they can be cut and stuck as a block
        for item_id in dict.fromkeys(data.item_ids):
            item = items[item_id]
            value = item.barcode or item.sku_code
            content = LabelContent(
                value,
                {"name": item.name, "barcode_text": value, "sku": item.sku_code, "uom": item.base_uom.code, "category": item.category or ""},
            )
            contents.extend([content] * data.copies)
        return label_pdf.render(layout, contents, data.skip, title="Item labels")

    def location_labels(self, data: LocationLabelRequest) -> bytes:
        layout, _ = self.layout("LOCATION", data.profile_id)
        base = select(Location).where(Location.tenant_id == self.tenant_id, Location.is_deleted == false())
        if data.location_ids:
            found = {loc.id: loc for loc in self.db.scalars(base.where(Location.id.in_(data.location_ids)))}
            missing = [str(i) for i in data.location_ids if i not in found]
            if missing:
                raise NotFoundError(f"Location not found: {', '.join(missing[:5])}")
            locations = [found[i] for i in dict.fromkeys(data.location_ids)]
        else:
            parent = self.db.scalars(base.where(Location.id == data.parent_id)).first()
            if parent is None:
                raise NotFoundError("Location not found")
            # Every bin and dock in that part of the tree (the parent itself too, when it holds stock), in code order
            # so the sheets come out in the order they are stuck on the racks
            locations = list(
                self.db.scalars(
                    base.where(
                        Location.is_active == true(),
                        Location.location_type.in_(STOCK_LOCATION_TYPES),
                        or_(Location.id == parent.id, Location.path.startswith(parent.path + "/", autoescape=True)),
                    ).order_by(Location.code)
                )
            )
            if not locations:
                raise DomainError(f"No bins or docks under {parent.code}")
        self._check_count(len(locations) * data.copies)
        contents = []
        for loc in locations:
            content = LabelContent(loc.code, {"code": loc.code, "name": loc.name, "path": loc.path})
            contents.extend([content] * data.copies)
        return label_pdf.render(layout, contents, data.skip, title="Location labels")


    def stock_labels(self, data: StockLabelRequest) -> bytes:
        """Labels for the cartons or pallets of a posted receipt, so later scans need no typing of batch or expiry"""
        layout, _ = self.layout("STOCK", data.profile_id)
        grn = get_document(self.db, self.tenant_id, DOC_GRN, data.grn_id)
        if grn.status != "POSTED":
            raise DomainError(f"Goods receipt {grn.doc_no} is not posted yet; print stock labels once the goods are received")
        # Stored as naive UTC; the label shows the warehouse's own date
        tenant = self.db.get(Tenant, self.tenant_id)
        received = (grn.posted_at or grn.created_at).replace(tzinfo=UTC).astimezone(ZoneInfo(tenant.default_timezone if tenant else "UTC"))
        source = f"{grn.doc_no} · {received:%Y-%m-%d}"
        contents = []
        for line in grn.lines:
            item = line.item
            sizes = self._split(line.qty_actual, data.qty_per_label)
            for size in sizes:
                code = label_pdf.stock_code(item.barcode or item.sku_code, line.batch_no, line.expiry_date, size)
                content = LabelContent(code, {
                    "name": item.name,
                    "sku": item.sku_code,
                    "batch": f"Batch {line.batch_no}" if line.batch_no else "",
                    "expiry": f"Exp {line.expiry_date:%Y-%m-%d}" if line.expiry_date else "",
                    "qty": f"{qty_text(size)} {line.uom.code}",
                    "source": source,
                })
                contents.extend([content] * data.copies)
        if not contents:
            raise DomainError(f"Goods receipt {grn.doc_no} has no lines")
        self._check_count(len(contents))
        return label_pdf.render(layout, contents, data.skip, title=f"Stock labels {grn.doc_no}")

    @staticmethod
    def _split(qty, per_label):
        """Quantities of the labels for one line: all of it, or full cartons of per_label and the rest"""
        if not per_label or per_label >= qty:
            return [qty]
        full, rest = divmod(qty, per_label)
        return [per_label] * int(full) + ([rest] if rest else [])

    def test_print(self, layout: LabelLayout) -> bytes:
        """One page (a few labels on a roll) of sample labels with each label's edge drawn, to line up a new
        profile with the label stock before saving it"""
        samples = label_pdf.sample_labels(layout.purpose)
        count = 3 if layout.media == "ROLL" else layout.columns * layout.rows
        contents = [samples[i % len(samples)] for i in range(count)]
        return label_pdf.render(layout, contents, outline=True, title="Label test print")

    @staticmethod
    def _check_count(count: int) -> None:
        if count > MAX_LABELS:
            raise DomainError(f"{count} labels requested; print at most {MAX_LABELS} at a time")

