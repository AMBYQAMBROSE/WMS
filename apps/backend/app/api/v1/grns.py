import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.document import DocumentRead, DocumentSummary, GrnIn
from app.services.grn_service import GrnService

router = APIRouter(prefix="/grns", tags=["grns"])


def _service(db: Session, user: CurrentUser) -> GrnService:
    return GrnService(db, user.tenant_id, user.id)


@router.get("", response_model=list[DocumentSummary])
def list_grns(
    status_filter: str | None = Query(default=None, alias="status"),
    po_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("grn.read")),
):
    return _service(db, user).list(
        status=status_filter, ref_document_id=po_id, skip=skip, limit=limit
    )


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def create_grn(
    data: GrnIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("grn.create")),
):
    return _service(db, user).create(data)


@router.get("/{grn_id}", response_model=DocumentRead)
def get_grn(
    grn_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("grn.read")),
):
    return _service(db, user).get(grn_id)


@router.post("/{grn_id}/post", response_model=DocumentRead)
def post_grn(
    grn_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("grn.post")),
):
    return _service(db, user).post(grn_id)


@router.post("/{grn_id}/cancel", response_model=DocumentRead)
def cancel_grn(
    grn_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("grn.cancel")),
):
    return _service(db, user).cancel(grn_id)
