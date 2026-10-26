import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.document import DocumentRead, DocumentSummary, PutawayIn
from app.services.putaway_service import PutawayService

router = APIRouter(prefix="/putaways", tags=["putaways"])


def _service(db: Session, user: CurrentUser) -> PutawayService:
    return PutawayService(db, user.tenant_id, user.id)


@router.get("", response_model=list[DocumentSummary])
def list_putaways(
    status_filter: str | None = Query(default=None, alias="status"),
    grn_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("putaway.read")),
):
    return _service(db, user).list(
        status=status_filter, ref_document_id=grn_id, skip=skip, limit=limit
    )


@router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
def create_putaway(
    data: PutawayIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("putaway.create")),
):
    return _service(db, user).create(data)


@router.get("/{putaway_id}", response_model=DocumentRead)
def get_putaway(
    putaway_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("putaway.read")),
):
    return _service(db, user).get(putaway_id)


@router.post("/{putaway_id}/post", response_model=DocumentRead)
def post_putaway(
    putaway_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("putaway.post")),
):
    return _service(db, user).post(putaway_id)


@router.post("/{putaway_id}/cancel", response_model=DocumentRead)
def cancel_putaway(
    putaway_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("putaway.cancel")),
):
    return _service(db, user).cancel(putaway_id)
