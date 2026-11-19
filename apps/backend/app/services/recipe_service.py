"""Recipes / bills of materials (feature RECIPES) and their costing.

Costing uses each component's latest purchase cost per base unit; a component that is never bought but has a recipe
itself (a sub-assembly) is costed from that recipe. How many units can be made comes from the components' available
stock (on hand - allocated, all locations), limited by the scarcest component.
"""

import uuid
from decimal import ROUND_FLOOR, Decimal

from sqlalchemy import false, func, or_, select, true
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, DomainError, NotFoundError
from app.models.recipe import Recipe, RecipeLine
from app.models.stock import StockBalance
from app.repositories.base import check_version
from app.schemas.recipe import RecipeIn
from app.services.analytics_service import AnalyticsService
from app.services.document_common import get_active_item, get_uom
from app.services.stock_service import to_base_qty

MAX_DEPTH = 5  # sub-assemblies inside sub-assemblies; deeper (or circular) recipes are not costed further
ZERO = Decimal(0)


class RecipeService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID | None, can_view_costs: bool = False):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.can_view_costs = can_view_costs

    def list(self, keyword: str | None = None, active_only: bool = False) -> list[Recipe]:
        stmt = select(Recipe).where(Recipe.tenant_id == self.tenant_id, Recipe.is_deleted == false())
        if kw := (keyword or "").strip():
            stmt = stmt.where(or_(Recipe.code.contains(kw, autoescape=True), Recipe.name.contains(kw, autoescape=True)))
        if active_only:
            stmt = stmt.where(Recipe.is_active == true())
        return list(self.db.scalars(stmt.order_by(Recipe.code)).unique())

    def get(self, recipe_id: uuid.UUID) -> Recipe:
        recipe = self.db.get(Recipe, recipe_id)
        if recipe is None or recipe.tenant_id != self.tenant_id or recipe.is_deleted:
            raise NotFoundError("Recipe not found")
        return recipe

    def create(self, data: RecipeIn) -> Recipe:
        code = data.code.strip()
        if self.db.scalar(select(Recipe.id).where(Recipe.tenant_id == self.tenant_id, Recipe.code == code)):
            raise ConflictError(f"Recipe code {code} already exists")
        recipe = Recipe(tenant_id=self.tenant_id, code=code, created_by=self.user_id)
        self._fill(recipe, data)
        self.db.add(recipe)
        self.db.flush()
        return recipe

    def update(self, recipe_id: uuid.UUID, data: RecipeIn) -> Recipe:
        recipe = self.get(recipe_id)
        check_version(recipe, data.row_version, f"Recipe {recipe.code}")
        recipe.lines.clear()
        self.db.flush()
        self._fill(recipe, data)
        recipe.row_version += 1
        self.db.flush()
        return recipe

    def delete(self, recipe_id: uuid.UUID) -> None:
        recipe = self.get(recipe_id)
        self.db.delete(recipe)
        self.db.flush()

    def _fill(self, recipe: Recipe, data: RecipeIn) -> None:
        product = get_active_item(self.db, self.tenant_id, data.product_item_id)
        seen = set()
        lines = []
        for line_no, line in enumerate(data.lines, start=1):
            item = get_active_item(self.db, self.tenant_id, line.item_id)
            if item.id == product.id:
                raise DomainError(f"Line {line_no}: {item.sku_code} is the product itself")
            get_uom(self.db, self.tenant_id, line.uom_id)
            to_base_qty(self.db, self.tenant_id, item, line.uom_id, line.qty)  # the unit must convert
            if (item.id, line.uom_id) in seen:
                raise DomainError(f"Line {line_no}: {item.sku_code} is listed twice in the same unit")
            seen.add((item.id, line.uom_id))
            lines.append(RecipeLine(
                tenant_id=self.tenant_id, line_no=line_no, item_id=item.id, uom_id=line.uom_id, qty=line.qty,
                created_by=self.user_id, updated_by=self.user_id,
            ))
        recipe.name = data.name.strip()
        recipe.product_item_id = product.id
        recipe.output_qty = data.output_qty
        recipe.remark = data.remark
        recipe.is_active = data.is_active
        recipe.updated_by = self.user_id
        recipe.lines.extend(lines)

    # ------------------------------------------------------------ costing

    def _available(self, item_ids) -> dict[uuid.UUID, Decimal]:
        item_ids = list(item_ids)
        if not item_ids:
            return {}
        B = StockBalance
        return {
            item_id: Decimal(qty)
            for item_id, qty in self.db.execute(
                select(B.item_id, func.sum(B.qty_on_hand - B.qty_allocated))
                .where(B.tenant_id == self.tenant_id, B.item_id.in_(item_ids))
                .group_by(B.item_id)
            )
        }

    def _unit_cost(self, recipe: Recipe, depth: int, path: frozenset) -> Decimal | None:
        """Cost of one base unit of the recipe's product; None when any component has no cost"""
        result = self._cost_lines(recipe, depth, path)
        if any(line["unit_cost"] is None for line in result):
            return None
        return sum((line["cost_per_unit"] for line in result), ZERO)

    def _cost_lines(self, recipe: Recipe, depth: int = 0, path: frozenset = frozenset()) -> list[dict]:
        analytics = AnalyticsService(self.db, self.tenant_id, True)
        latest = analytics.latest_costs(line.item_id for line in recipe.lines)
        path = path | {recipe.product_item_id}
        lines = []
        for line in recipe.lines:
            base = to_base_qty(self.db, self.tenant_id, line.item, line.uom_id, line.qty)
            per_unit = base / recipe.output_qty
            cost, source = None, None
            if line.item_id in latest:
                cost, source = latest[line.item_id][0], "purchase"
            elif depth < MAX_DEPTH and line.item_id not in path:
                sub = self.db.scalar(
                    select(Recipe).where(
                        Recipe.tenant_id == self.tenant_id, Recipe.product_item_id == line.item_id,
                        Recipe.is_active == true(), Recipe.is_deleted == false(),
                    ).order_by(Recipe.code).limit(1)
                )
                if sub is not None:
                    cost = self._unit_cost(sub, depth + 1, path)
                    source = f"recipe {sub.code}" if cost is not None else None
            lines.append({
                "line": line,
                "base_qty": base,
                "qty_per_unit": per_unit,
                "unit_cost": cost,
                "cost_source": source,
                "cost_per_unit": per_unit * cost if cost is not None else None,
            })
        return lines

    def costing(self, recipe: Recipe) -> dict:
        cost_lines = self._cost_lines(recipe)
        available = self._available(line["line"].item_id for line in cost_lines)
        complete = all(line["unit_cost"] is not None for line in cost_lines)
        total = sum((line["cost_per_unit"] or ZERO for line in cost_lines), ZERO)
        makeable, bottleneck = None, None
        result_lines = []
        for c in cost_lines:
            line = c["line"]
            avail = available.get(line.item_id, ZERO)
            can_make = (max(avail, ZERO) / c["qty_per_unit"]).to_integral_value(ROUND_FLOOR) if c["qty_per_unit"] > 0 else None
            if can_make is not None and (makeable is None or can_make < makeable):
                makeable, bottleneck = can_make, line.item
            show = self.can_view_costs
            result_lines.append({
                "line_no": line.line_no,
                "item": line.item,
                "uom": line.uom,
                "qty": line.qty,
                "base_qty": c["base_qty"],
                "qty_per_unit": c["qty_per_unit"],
                "available": avail,
                "can_make": can_make,
                "unit_cost": c["unit_cost"] if show else None,
                "cost_source": c["cost_source"],
                "cost_per_unit": c["cost_per_unit"] if show else None,
                "share_pct": (round(c["cost_per_unit"] / total * 100, 1) if show and total and c["cost_per_unit"] is not None else None),
            })
        return {
            "recipe_id": recipe.id,
            "complete": complete,
            "missing_costs": [c["line"].item.sku_code for c in cost_lines if c["unit_cost"] is None],
            "unit_cost": total if self.can_view_costs and cost_lines else None,
            "batch_cost": total * recipe.output_qty if self.can_view_costs and cost_lines else None,
            "can_make": makeable if makeable is not None else ZERO,
            "bottleneck": bottleneck,
            "lines": result_lines,
        }

    def overview(self) -> list[dict]:
        """Every active recipe with its unit cost and how many units stock can make (dashboard card)"""
        result = []
        for recipe in self.list(active_only=True):
            costing = self.costing(recipe)
            result.append({
                "id": recipe.id, "code": recipe.code, "name": recipe.name, "product": recipe.product,
                "unit_cost": costing["unit_cost"], "complete": costing["complete"],
                "can_make": costing["can_make"], "bottleneck": costing["bottleneck"],
                "components": len(recipe.lines),
            })
        return result
