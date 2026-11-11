import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.api.routing import TransactionalRoute
from app.services.document_report_service import DocumentReportService

router = APIRouter(route_class=TransactionalRoute, prefix="/documents", tags=["printing"])


@router.get(
    "/{document_id}/print",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The document's A4 report as PDF"}},
)
def print_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    # Needs read permission on the document's type (checked in the service, which knows the type)
    user: CurrentUser = Depends(get_current_user),
):
    """The printed copy of any document: details, lines, totals and signature boxes, with the document number as a
    barcode on every page. Each print is recorded in the document's history."""
    content, filename = DocumentReportService(db, user).pdf(document_id)
    return Response(
        content, media_type="application/pdf", headers={"Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"}
    )
