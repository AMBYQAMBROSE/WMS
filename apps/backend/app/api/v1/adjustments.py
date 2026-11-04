import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.filters import document_filters
from app.schemas.document import AdjustmentIn, DocumentRead, DocumentSummary
from app.services.adjustment_service import AdjustmentService

router = APIRouter(prefix="/adjustments", tags=["adjustments"])


def _service(db: Session, user: CurrentUser) -> AdjustmentService:
    return AdjustmentService(db, user.tenant_id, user.id)


@router.get("", response_model=list[DocumentSummary])
def list_adjustments(
    filters: dict = Depends(document_filters),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("adjustment.read")),
):
    return _service(db, user).list(**filters)


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def create_adjustment(
    data: AdjustmentIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("adjustment.create")),
):
    return _service(db, user).create(data)


@router.get("/{document_id}", response_model=DocumentRead)
def get_adjustment(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("adjustment.read")),
):
    return _service(db, user).get(document_id)


@router.post("/{document_id}/post", response_model=DocumentRead)
def post_adjustment(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("adjustment.post")),
):
    return _service(db, user).post(document_id)


@router.post("/{document_id}/cancel", response_model=DocumentRead)
def cancel_adjustment(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("adjustment.cancel")),
):
    return _service(db, user).cancel(document_id)
