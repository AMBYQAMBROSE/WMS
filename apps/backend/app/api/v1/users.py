import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.user import PasswordReset, UserCreate, UserRead, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


def _service(db: Session, user: CurrentUser) -> UserService:
    return UserService(db, user.tenant_id, user.id)


@router.get("", response_model=list[UserRead])
def list_users(
    skip: int = 0,
    limit: int = Query(default=200, le=500),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("user.read")),
):
    return _service(db, current_user).list(skip, limit)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("user.create")),
):
    return _service(db, current_user).create(data)


@router.put("/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("user.update")),
):
    return _service(db, current_user).update(user_id, data)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: uuid.UUID,
    data: PasswordReset,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("user.update")),
) -> None:
    _service(db, current_user).reset_password(user_id, data.password)
