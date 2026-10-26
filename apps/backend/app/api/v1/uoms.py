from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.models.item import Uom
from app.repositories.base import BaseRepository
from app.schemas.document import UomBrief

router = APIRouter(prefix="/uoms", tags=["uoms"])


@router.get("", response_model=list[UomBrief])
def list_uoms(
    skip: int = 0,
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("uom.read")),
):
    return BaseRepository(db, Uom).list(user.tenant_id, skip, limit)
