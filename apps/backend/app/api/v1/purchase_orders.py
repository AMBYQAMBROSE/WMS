import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.document import DocumentRead, DocumentSummary, PurchaseOrderIn
from app.services.purchase_order_service import PurchaseOrderService

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])


def _service(db: Session, user: CurrentUser) -> PurchaseOrderService:
    return PurchaseOrderService(db, user.tenant_id, user.id)


@router.get("", response_model=list[DocumentSummary])
def list_purchase_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    partner_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("purchase_order.read")),
):
    return _service(db, user).list(
        status=status_filter, partner_id=partner_id, skip=skip, limit=limit
    )


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    data: PurchaseOrderIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("purchase_order.create")),
):
    return _service(db, user).create(data)


@router.get("/{po_id}", response_model=DocumentRead)
def get_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("purchase_order.read")),
):
    return _service(db, user).get(po_id)


@router.put("/{po_id}", response_model=DocumentRead)
def update_purchase_order(
    po_id: uuid.UUID,
    data: PurchaseOrderIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("purchase_order.update")),
):
    return _service(db, user).update(po_id, data)


@router.post("/{po_id}/confirm", response_model=DocumentRead)
def confirm_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("purchase_order.confirm")),
):
    return _service(db, user).confirm(po_id)


@router.post("/{po_id}/cancel", response_model=DocumentRead)
def cancel_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("purchase_order.cancel")),
):
    return _service(db, user).cancel(po_id)


@router.post("/{po_id}/close", response_model=DocumentRead)
def close_purchase_order(
    po_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("purchase_order.close")),
):
    return _service(db, user).close(po_id)
