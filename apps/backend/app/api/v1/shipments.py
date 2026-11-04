import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.filters import document_filters
from app.schemas.document import DocumentSummary
from app.schemas.outbound import ShipmentCreate, ShipmentInfoIn, ShipmentRead
from app.services.shipment_service import ShipmentService

router = APIRouter(prefix="/shipments", tags=["shipments"])


def _service(db: Session, user: CurrentUser) -> ShipmentService:
    return ShipmentService(db, user.tenant_id, user.id)


@router.get("", response_model=list[DocumentSummary])
def list_shipments(
    filters: dict = Depends(document_filters),
    so_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("shipment.read")),
):
    return _service(db, user).list(**filters, ref_document_id=so_id)


@router.post("", response_model=ShipmentRead, status_code=status.HTTP_201_CREATED)
def create_shipment(
    data: ShipmentCreate,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("shipment.create")),
):
    return _service(db, user).create(data)


@router.get("/{ship_id}", response_model=ShipmentRead)
def get_shipment(
    ship_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("shipment.read")),
):
    return _service(db, user).get(ship_id)


@router.put("/{ship_id}/info", response_model=ShipmentRead)
def update_shipment_info(
    ship_id: uuid.UUID,
    data: ShipmentInfoIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("shipment.create")),
):
    return _service(db, user).update_info(ship_id, data)


@router.post("/{ship_id}/post", response_model=ShipmentRead)
def post_shipment(
    ship_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("shipment.post")),
):
    return _service(db, user).post(ship_id)


@router.post("/{ship_id}/cancel", response_model=ShipmentRead)
def cancel_shipment(
    ship_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("shipment.cancel")),
):
    return _service(db, user).cancel(ship_id)
