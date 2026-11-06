import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.filters import document_filters
from app.api.routing import TransactionalRoute
from app.schemas.document import DocumentSummary
from app.schemas.outbound import PickConfirmIn, PickRead
from app.services.pick_service import PickService

router = APIRouter(route_class=TransactionalRoute, prefix="/picks", tags=["picks"])


def _service(db: Session, user: CurrentUser) -> PickService:
    return PickService(db, user.tenant_id, user.id)


@router.get("", response_model=list[DocumentSummary])
def list_picks(
    filters: dict = Depends(document_filters),
    so_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("pick.read")),
):
    return _service(db, user).list(**filters, ref_document_id=so_id)


@router.get("/{pick_id}", response_model=PickRead)
def get_pick(
    pick_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("pick.read")),
):
    return _service(db, user).get(pick_id)


@router.post("/{pick_id}/lines/{line_id}/confirm", response_model=PickRead)
def confirm_pick_line(
    pick_id: uuid.UUID,
    line_id: uuid.UUID,
    data: PickConfirmIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("pick.confirm")),
):
    return _service(db, user).confirm_line(pick_id, line_id, data.qty)


@router.post("/{pick_id}/confirm-all", response_model=PickRead)
def confirm_all_pick_lines(
    pick_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("pick.confirm")),
):
    return _service(db, user).confirm_all(pick_id)


@router.post("/{pick_id}/post", response_model=PickRead)
def post_pick(
    pick_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("pick.post")),
):
    return _service(db, user).post(pick_id)


@router.post("/{pick_id}/cancel", response_model=PickRead)
def cancel_pick(
    pick_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("pick.cancel")),
):
    return _service(db, user).cancel(pick_id)
