import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.schemas.audit import AuditLogRead
from app.services.audit_service import AuditService

router = APIRouter(route_class=TransactionalRoute, prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    entity_id: uuid.UUID | None = Query(default=None, description="A record; for a document, also its lines"),
    entity_type: str | None = None,
    user_id: uuid.UUID | None = None,
    action: Literal["CREATE", "UPDATE", "DELETE", "PRINT"] | None = None,
    keyword: str | None = Query(default=None, description="Part of the record's code or document number"),
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("audit.read")),
):
    return AuditService(db, user.tenant_id).list(
        entity_id=entity_id, entity_type=entity_type, user_id=user_id, action=action, keyword=keyword,
        occurred_from=occurred_from, occurred_to=occurred_to, skip=skip, limit=limit,
    )
