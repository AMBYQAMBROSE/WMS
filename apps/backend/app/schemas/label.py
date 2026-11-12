import json
import uuid
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, field_validator, model_validator

from app.schemas.versioning import ExpectedVersion

Purpose = Literal["ITEM", "LOCATION", "STOCK"]

# Text fields a label of each purpose can show besides the barcode, in the order offered to the user
LABEL_FIELDS: dict[str, list[tuple[str, str]]] = {
    "ITEM": [
        ("name", "Item name"),
        ("barcode_text", "Barcode digits"),
        ("sku", "SKU"),
        ("uom", "Base unit"),
        ("category", "Category"),
    ],
    "LOCATION": [
        ("code", "Location code (large)"),
        ("name", "Location name"),
        ("path", "Location path"),
    ],
    # Stock label: one carton or pallet of a receipt; its code carries item, batch, expiry and quantity
    "STOCK": [
        ("name", "Item name"),
        ("sku", "SKU"),
        ("batch", "Batch no."),
        ("expiry", "Expiry date"),
        ("qty", "Quantity"),
        ("source", "Receipt no. and date"),
    ],
}

# Millimetres, sent to clients as JSON numbers (a plain Decimal would be a string)
_AsNumber = PlainSerializer(float, return_type=float, when_used="json")
Mm = Annotated[Decimal, Field(ge=0, le=1000, max_digits=7, decimal_places=2), _AsNumber]
PositiveMm = Annotated[Decimal, Field(gt=0, le=1000, max_digits=7, decimal_places=2), _AsNumber]
PaddingMm = Annotated[Decimal, Field(ge=0, le=50, max_digits=7, decimal_places=2), _AsNumber]


class LabelLayout(BaseModel):
    """Everything that decides how a label prints. Also the body of a test print, so a layout can be checked on
    paper before it is saved."""

    purpose: Purpose
    media: Literal["SHEET", "ROLL"]
    label_width_mm: PositiveMm
    label_height_mm: PositiveMm
    # A4 unless set
    page_width_mm: PositiveMm = Decimal("210")
    page_height_mm: PositiveMm = Decimal("297")
    columns: int = Field(default=1, ge=1, le=20)
    rows: int = Field(default=1, ge=1, le=50)
    margin_top_mm: Mm = Decimal(0)
    margin_left_mm: Mm = Decimal(0)
    gap_x_mm: Mm = Decimal(0)
    gap_y_mm: Mm = Decimal(0)
    padding_mm: PaddingMm = Decimal(2)
    barcode_type: Literal["CODE128", "QR"] = "CODE128"
    fields: list[str] = Field(default_factory=list, max_length=10)
    font_size: int = Field(default=9, ge=5, le=72)

    @field_validator("fields", mode="before")
    @classmethod
    def _parse_fields(cls, value):
        # Stored as JSON text in the database
        return json.loads(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check(self):
        allowed = {code for code, _ in LABEL_FIELDS[self.purpose]}
        unknown = [f for f in self.fields if f not in allowed]
        if unknown:
            raise ValueError(f"Unknown label fields for {self.purpose}: {', '.join(unknown)}")
        if len(set(self.fields)) != len(self.fields):
            raise ValueError("A label field is listed twice")
        if 2 * self.padding_mm >= min(self.label_width_mm, self.label_height_mm):
            raise ValueError("Padding leaves no room on the label")
        if self.media == "SHEET":
            used_w = self.margin_left_mm + self.columns * self.label_width_mm + (self.columns - 1) * self.gap_x_mm
            used_h = self.margin_top_mm + self.rows * self.label_height_mm + (self.rows - 1) * self.gap_y_mm
            if used_w > self.page_width_mm:
                raise ValueError(f"Labels are {used_w} mm wide with margin and gaps, wider than the {self.page_width_mm} mm page")
            if used_h > self.page_height_mm:
                raise ValueError(f"Labels are {used_h} mm tall with margin and gaps, taller than the {self.page_height_mm} mm page")
        return self


class LabelProfileIn(LabelLayout):
    name: str = Field(min_length=1, max_length=100)
    is_default: bool = False


class LabelProfileUpdate(LabelProfileIn, ExpectedVersion):
    pass


class LabelProfileRead(LabelProfileIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    row_version: int


class LabelFieldOption(BaseModel):
    code: str
    name: str


class ItemLabelRequest(BaseModel):
    item_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    copies: int = Field(default=1, ge=1, le=500)
    profile_id: uuid.UUID | None = None
    # Label positions to leave blank at the start of the first sheet, to reuse a partly used label sheet
    skip: int = Field(default=0, ge=0, le=999)


class StockLabelRequest(BaseModel):
    """Stock labels for the lines of a posted receipt: one label per line, or with qty_per_label one per carton or
    pallet of that size (the last one holds the rest)"""

    grn_id: uuid.UUID
    qty_per_label: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    copies: int = Field(default=1, ge=1, le=20)
    profile_id: uuid.UUID | None = None
    skip: int = Field(default=0, ge=0, le=999)


class LocationLabelRequest(BaseModel):
    """Either the chosen locations, or every bin and dock under one location (a zone, an aisle, a rack)"""

    location_ids: list[uuid.UUID] | None = Field(default=None, max_length=2000)
    parent_id: uuid.UUID | None = None
    copies: int = Field(default=1, ge=1, le=20)
    profile_id: uuid.UUID | None = None
    skip: int = Field(default=0, ge=0, le=999)

    @model_validator(mode="after")
    def _one_source(self):
        if bool(self.location_ids) == (self.parent_id is not None):
            raise ValueError("Give either location_ids or parent_id")
        return self
