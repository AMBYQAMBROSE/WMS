import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.filters import document_filters
from app.api.routing import TransactionalRoute
from app.schemas.document import DocumentRead, DocumentSummary, PutawayPutIn, TransferIn
from app.services.transfer_service import MoveService, PutawayService, TransferService


def make_transfer_router(
    prefix: str, service_cls: type[TransferService], permission: str, tag: str
) -> APIRouter:
    """Putaway and move share exactly the same API; only the service class and permission prefix differ.
    Lists can be filtered by source document with ref_document_id (a putaway's source is a goods receipt).
    """
    router = APIRouter(route_class=TransactionalRoute, prefix=prefix, tags=[tag])

    def service(db: Session, user: CurrentUser) -> TransferService:
        return service_cls(db, user.tenant_id, user.id)

    @router.get("", response_model=list[DocumentSummary])
    def list_documents(
        filters: dict = Depends(document_filters),
        ref_document_id: uuid.UUID | None = None,
        grn_id: uuid.UUID | None = Query(default=None, description="Legacy parameter, same as ref_document_id"),
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.read")),
    ):
        return service(db, user).list(
            **filters, ref_document_id=ref_document_id or grn_id
        )

    @router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
    def create_document(
        data: TransferIn,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.create")),
    ):
        return service(db, user).create(data)

    @router.get("/{document_id}", response_model=DocumentRead)
    def get_document(
        document_id: uuid.UUID,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.read")),
    ):
        return service(db, user).get(document_id)

    @router.post("/{document_id}/post", response_model=DocumentRead)
    def post_document(
        document_id: uuid.UUID,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.post")),
    ):
        return service(db, user).post(document_id)

    @router.post("/{document_id}/cancel", response_model=DocumentRead)
    def cancel_document(
        document_id: uuid.UUID,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.cancel")),
    ):
        return service(db, user).cancel(document_id)

    return router


putaway_router = make_transfer_router("/putaways", PutawayService, "putaway", "putaways")
move_router = make_transfer_router("/moves", MoveService, "move", "moves")


@putaway_router.post("/{document_id}/lines/{line_id}/put", response_model=DocumentRead)
def put_away_line(
    document_id: uuid.UUID,
    line_id: uuid.UUID,
    data: PutawayPutIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("putaway.create")),
):
    """Putaway sheet (status TO_PUT_AWAY): record the quantity of a line placed in a bin. Less than the line's
    quantity splits off the rest as a new open line. Post the sheet once every line is done."""
    return PutawayService(db, user.tenant_id, user.id).put(document_id, line_id, data.to_location_id, data.qty)
