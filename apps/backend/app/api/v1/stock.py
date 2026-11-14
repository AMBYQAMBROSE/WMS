import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.schemas.document import StockBalanceRead, StockLedgerRead
from app.services import stock_service

router = APIRouter(route_class=TransactionalRoute, prefix="/stock", tags=["stock"])


@router.get("/balances", response_model=list[StockBalanceRead])
def list_stock_balances(
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    unavailable: bool = Query(default=False, description="Only balances with nothing available (on hand minus allocated <= 0)"),
    skip: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    return stock_service.list_balances(db, user.tenant_id, item_id, location_id, skip, limit, unavailable=unavailable)


@router.get("/ledger", response_model=list[StockLedgerRead])
def list_stock_ledger(
    item_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    movement_type: str | None = Query(default=None, max_length=30),
    skip: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    return stock_service.list_ledger(db, user.tenant_id, item_id, location_id, skip, limit, movement_type=movement_type)
