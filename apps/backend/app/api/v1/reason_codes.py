import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.models.reason_code import ReasonCode
from app.repositories.base import BaseRepository, check_version
from app.schemas.document import ReasonCodeIn, ReasonCodeRead
from app.services.master_guard import delete_reason

router = APIRouter(route_class=TransactionalRoute, prefix="/reason-codes", tags=["reason-codes"])


@router.get("", response_model=list[ReasonCodeRead])
def list_reason_codes(
    category: str | None = None,
    active_only: bool = False,
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("reason_code.read")),
):
    reasons = BaseRepository(db, ReasonCode).list(user.tenant_id, 0, limit)
    return [
        r
        for r in reasons
        if (category is None or r.category == category) and (not active_only or r.is_active)
    ]


@router.post("", response_model=ReasonCodeRead, status_code=status.HTTP_201_CREATED)
def create_reason_code(
    data: ReasonCodeIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("reason_code.create")),
):
    reason = ReasonCode(
        tenant_id=user.tenant_id, created_by=user.id, updated_by=user.id, **data.model_dump(exclude={"row_version"})
    )
    return BaseRepository(db, ReasonCode).create(reason)


@router.put("/{reason_id}", response_model=ReasonCodeRead)
def update_reason_code(
    reason_id: uuid.UUID,
    data: ReasonCodeIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("reason_code.update")),
):
    repo = BaseRepository(db, ReasonCode)
    reason = repo.get(user.tenant_id, reason_id)
    if reason is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reason code not found")
    check_version(reason, data.row_version, f"Reason code {reason.code}")
    return repo.update(reason, {**data.model_dump(exclude={"row_version"}), "updated_by": user.id})


@router.delete("/{reason_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reason_code(
    reason_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("reason_code.delete")),
) -> None:
    repo = BaseRepository(db, ReasonCode)
    reason = repo.get(user.tenant_id, reason_id)
    if reason is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reason code not found")
    delete_reason(db, reason)
