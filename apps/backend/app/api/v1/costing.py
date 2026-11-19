"""Supplier payables (cost.view) and recipes (feature RECIPES)."""

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_feature, require_permission
from app.api.routing import TransactionalRoute
from app.core.feature_catalog import FEATURE_RECIPES
from app.schemas.document import DocumentRead
from app.schemas.recipe import RecipeCosting, RecipeIn, RecipeOverview, RecipeRead
from app.schemas.report import PayablePage, SettleIn
from app.services.payable_service import PayableService
from app.services.recipe_service import RecipeService

payable_router = APIRouter(route_class=TransactionalRoute, prefix="/payables", tags=["payables"])


@payable_router.get("", response_model=PayablePage)
def list_payables(
    status_: Literal["open", "overdue", "settled"] | None = Query(default=None, alias="status"),
    partner_id: uuid.UUID | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cost.view")),
):
    """Posted goods receipts with their due date and value; open ones most urgent first"""
    return PayableService(db, user.tenant_id, user.id).list(status_, partner_id, limit)


@payable_router.post("/{grn_id}/settle", response_model=DocumentRead)
def settle_payable(
    grn_id: uuid.UUID,
    data: SettleIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("payable.settle")),
):
    return PayableService(db, user.tenant_id, user.id).settle(grn_id, data.settled_on)


@payable_router.post("/{grn_id}/reopen", response_model=DocumentRead)
def reopen_payable(
    grn_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("payable.settle")),
):
    return PayableService(db, user.tenant_id, user.id).reopen(grn_id)


recipe_router = APIRouter(
    route_class=TransactionalRoute,
    prefix="/recipes",
    tags=["recipes"],
    dependencies=[Depends(require_feature(FEATURE_RECIPES))],
)


def _recipes(db: Session, user: CurrentUser) -> RecipeService:
    return RecipeService(db, user.tenant_id, user.id, "cost.view" in user.permissions)


@recipe_router.get("", response_model=list[RecipeRead])
def list_recipes(
    keyword: str | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recipe.read")),
):
    return _recipes(db, user).list(keyword)


@recipe_router.get("/overview", response_model=list[RecipeOverview])
def recipe_overview(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recipe.read")),
):
    """Active recipes with cost per unit (cost.view) and how many units current stock can make"""
    return _recipes(db, user).overview()


@recipe_router.post("", response_model=RecipeRead, status_code=status.HTTP_201_CREATED)
def create_recipe(
    data: RecipeIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recipe.manage")),
):
    return _recipes(db, user).create(data)


@recipe_router.get("/{recipe_id}", response_model=RecipeRead)
def get_recipe(
    recipe_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recipe.read")),
):
    return _recipes(db, user).get(recipe_id)


@recipe_router.get("/{recipe_id}/costing", response_model=RecipeCosting)
def recipe_costing(
    recipe_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recipe.read")),
):
    """Cost components (latest purchase cost of each), cost share, and how many units each component's stock allows"""
    service = _recipes(db, user)
    return service.costing(service.get(recipe_id))


@recipe_router.put("/{recipe_id}", response_model=RecipeRead)
def update_recipe(
    recipe_id: uuid.UUID,
    data: RecipeIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recipe.manage")),
):
    return _recipes(db, user).update(recipe_id, data)


@recipe_router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(
    recipe_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recipe.manage")),
):
    _recipes(db, user).delete(recipe_id)
