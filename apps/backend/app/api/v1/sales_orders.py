import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.core.feature_catalog import FEATURE_CROSS_DOCK
from app.schemas.document import DocumentSummary
from app.schemas.outbound import (
    AllocateIn,
    AllocationResult,
    PickRead,
    SalesOrderIn,
    SalesOrderRead,
    ShortageReportRow,
)
from app.services.document_common import is_feature_enabled
from app.services.sales_order_service import SalesOrderService

router = APIRouter(prefix="/sales-orders", tags=["sales-orders"])


def _service(db: Session, user: CurrentUser) -> SalesOrderService:
    return SalesOrderService(db, user.tenant_id, user.id)


@router.get("", response_model=list[DocumentSummary])
def list_sales_orders(
    status_filter: str | None = Query(default=None, alias="status"),
    partner_id: uuid.UUID | None = None,
    doc_no: str | None = None,
    skip: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.read")),
):
    return _service(db, user).list(
        status=status_filter, partner_id=partner_id, doc_no=doc_no, skip=skip, limit=limit
    )


@router.get("/shortages", response_model=list[ShortageReportRow])
def shortage_report(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.read")),
):
    """Quantity not yet allocated across all orders in progress (Ninso OrderShortage)"""
    return _service(db, user).shortage_report()


@router.post("", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED)
def create_sales_order(
    data: SalesOrderIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.create")),
):
    service = _service(db, user)
    return service.read(service.create(data))


@router.get("/{so_id}", response_model=SalesOrderRead)
def get_sales_order(
    so_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.read")),
):
    service = _service(db, user)
    return service.read(service.get(so_id))


@router.put("/{so_id}", response_model=SalesOrderRead)
def update_sales_order(
    so_id: uuid.UUID,
    data: SalesOrderIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.update")),
):
    service = _service(db, user)
    return service.read(service.update(so_id, data))


@router.post("/{so_id}/confirm", response_model=SalesOrderRead)
def confirm_sales_order(
    so_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.confirm")),
):
    service = _service(db, user)
    return service.read(service.confirm(so_id))


@router.post("/{so_id}/allocate", response_model=AllocationResult)
def allocate_sales_order(
    so_id: uuid.UUID,
    data: AllocateIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.allocate")),
):
    if data.source_location_id is not None and not is_feature_enabled(db, user.tenant_id, FEATURE_CROSS_DOCK):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Feature not enabled: cross-docking")
    pick, shortages = _service(db, user).allocate(so_id, data.staging_location_id, data.source_location_id)
    return AllocationResult(pick=PickRead.model_validate(pick), shortages=shortages)


@router.post("/{so_id}/cancel", response_model=SalesOrderRead)
def cancel_sales_order(
    so_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.cancel")),
):
    service = _service(db, user)
    return service.read(service.cancel(so_id))


@router.post("/{so_id}/close", response_model=SalesOrderRead)
def close_sales_order(
    so_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("sales_order.close")),
):
    service = _service(db, user)
    return service.read(service.close(so_id))
