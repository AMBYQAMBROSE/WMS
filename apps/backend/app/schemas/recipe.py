import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document import ItemBrief, PositiveQty, Price, Qty, UomBrief
from app.schemas.versioning import ExpectedVersion


class RecipeLineIn(BaseModel):
    item_id: uuid.UUID
    uom_id: uuid.UUID
    qty: PositiveQty


class RecipeIn(ExpectedVersion):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    product_item_id: uuid.UUID
    # Batch size the component quantities make, in the product's base unit
    output_qty: PositiveQty
    remark: str | None = Field(default=None, max_length=400)
    is_active: bool = True
    lines: list[RecipeLineIn] = Field(min_length=1, max_length=200)


class RecipeLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    line_no: int
    item: ItemBrief
    uom: UomBrief
    qty: Qty


class RecipeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    product: ItemBrief
    output_qty: Qty
    remark: str | None
    is_active: bool
    row_version: int
    updated_at: datetime
    lines: list[RecipeLineRead]


class RecipeCostLine(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line_no: int
    item: ItemBrief
    uom: UomBrief
    qty: Qty
    base_qty: Qty
    # Component base units needed for one base unit of the product
    qty_per_unit: Qty
    available: Qty
    # Units of product this component's available stock alone could make
    can_make: Qty | None
    # Cost of one component base unit, and where it came from ("purchase" = latest receipt, or "recipe XYZ")
    unit_cost: Price = None
    cost_source: str | None
    cost_per_unit: Price = None
    share_pct: Qty | None


class RecipeCosting(BaseModel):
    recipe_id: uuid.UUID
    complete: bool
    missing_costs: list[str]
    unit_cost: Price = None
    batch_cost: Price = None
    can_make: Qty
    bottleneck: ItemBrief | None
    lines: list[RecipeCostLine]


class RecipeOverview(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    product: ItemBrief
    unit_cost: Price = None
    complete: bool
    can_make: Qty
    bottleneck: ItemBrief | None
    components: int
