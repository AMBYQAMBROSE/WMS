import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.api.routing import TransactionalRoute
from app.schemas.attachment import AttachmentIn, AttachmentRead
from app.services.attachment_service import AttachmentService

# Permissions depend on the document's type, so they are checked in AttachmentService, not per route
router = APIRouter(route_class=TransactionalRoute, tags=["attachments"])


@router.get("/documents/{document_id}/attachments", response_model=list[AttachmentRead])
def list_attachments(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    return AttachmentService(db, user).list(document_id)


@router.post("/documents/{document_id}/attachments", response_model=AttachmentRead, status_code=status.HTTP_201_CREATED)
def add_attachment(
    document_id: uuid.UUID,
    data: AttachmentIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    return AttachmentService(db, user).add(document_id, data.content_base64, data.caption)


@router.get("/attachments/{attachment_id}/content", response_class=Response)
def attachment_content(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    attachment = AttachmentService(db, user).content(attachment_id)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={
            # A photo never changes once stored; the browser may keep it, but only for this user
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'inline; filename="{attachment.file_name}"',
        },
    )


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    AttachmentService(db, user).delete(attachment_id)
