from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.v1.health import CODE_REVISION
from app.schemas.system import SystemStatus
from app.services.system_service import system_status

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
def get_system_status(
    request: Request,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("system.settings")),
):
    return system_status(
        db, user.tenant_id, code_revision=CODE_REVISION, otel_enabled=getattr(request.app.state, "otel_enabled", False)
    )
