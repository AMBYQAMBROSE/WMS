import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.models.document import DocumentHeader
from app.schemas.document import CountEntryIn, CountRead, CycleCountCreate, DocumentSummary, RecountIn
from app.services.cycle_count_service import CycleCountService

router = APIRouter(prefix="/cycle-counts", tags=["cycle-counts"])

VIEW_EXPECTED = "cycle_count.view_expected"


def _service(db: Session, user: CurrentUser) -> CycleCountService:
    return CycleCountService(db, user.tenant_id, user.id)


def _read(document: DocumentHeader, user: CurrentUser) -> CountRead:
    """Blind count: people without permission to see book quantities do not see them, so they cannot just "count" the book figures"""
    read = CountRead.model_validate(document)
    if VIEW_EXPECTED not in user.permissions:
        for line in read.lines:
            line.qty_planned = None
    return read


@router.get("", response_model=list[DocumentSummary])
def list_cycle_counts(
    status_filter: str | None = Query(default=None, alias="status"),
    skip: int = 0,
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cycle_count.read")),
):
    return _service(db, user).list(status=status_filter, skip=skip, limit=limit)


@router.post("", response_model=CountRead, status_code=status.HTTP_201_CREATED)
def create_cycle_count(
    data: CycleCountCreate,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cycle_count.create")),
):
    return _read(_service(db, user).create(data), user)


@router.get("/{document_id}", response_model=CountRead)
def get_cycle_count(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cycle_count.read")),
):
    return _read(_service(db, user).get(document_id), user)


@router.post("/{document_id}/counts", response_model=CountRead)
def record_count(
    document_id: uuid.UUID,
    entry: CountEntryIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cycle_count.count")),
):
    return _read(_service(db, user).record(document_id, entry), user)


@router.post("/{document_id}/recount", response_model=CountRead)
def request_recount(
    document_id: uuid.UUID,
    data: RecountIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cycle_count.post")),
):
    return _read(_service(db, user).recount(document_id, data.line_ids), user)


@router.post("/{document_id}/post", response_model=CountRead)
def post_cycle_count(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cycle_count.post")),
):
    return _read(_service(db, user).post(document_id), user)


@router.post("/{document_id}/cancel", response_model=CountRead)
def cancel_cycle_count(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("cycle_count.cancel")),
):
    return _read(_service(db, user).cancel(document_id), user)
