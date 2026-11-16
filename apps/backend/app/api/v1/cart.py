"""Shopping cart endpoints. Need only cart.order: a customer account can order without item, partner or sales order permissions."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.schemas.cart import CartOrderIn, CatalogPage
from app.schemas.document import DocumentSummary, PartnerBrief
from app.schemas.outbound import SalesOrderRead
from app.services.cart_service import CartService

router = APIRouter(route_class=TransactionalRoute, prefix="/cart", tags=["cart"])

CartUser = Depends(require_permission("cart.order"))


@router.get("/catalog", response_model=CatalogPage)
def catalog(
    keyword: str | None = None,
    category: str | None = None,
    in_stock_only: bool = False,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=48, ge=1, le=200),
    db: Session = Depends(get_db_session),
    user: CurrentUser = CartUser,
):
    return CartService(db, user).catalog(keyword, category, in_stock_only, skip, limit)


@router.get("/customers", response_model=list[PartnerBrief])
def customers(
    keyword: str | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = CartUser,
):
    return CartService(db, user).customers(keyword)


@router.post("/orders", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED)
def submit_order(data: CartOrderIn, db: Session = Depends(get_db_session), user: CurrentUser = CartUser):
    return CartService(db, user).submit(data)


@router.get("/orders", response_model=list[DocumentSummary])
def my_orders(
    status: str | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    user: CurrentUser = CartUser,
):
    return CartService(db, user).orders(status, skip, limit)


@router.get("/orders/{so_id}", response_model=SalesOrderRead)
def my_order(so_id: uuid.UUID, db: Session = Depends(get_db_session), user: CurrentUser = CartUser):
    return CartService(db, user).order(so_id)


@router.post("/orders/{so_id}/cancel", response_model=SalesOrderRead)
def cancel_my_order(so_id: uuid.UUID, db: Session = Depends(get_db_session), user: CurrentUser = CartUser):
    return CartService(db, user).cancel(so_id)
