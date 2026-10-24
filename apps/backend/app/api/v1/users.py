from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("user.read")),
) -> list[UserRead]:
    return UserService(db).list(current_user.tenant_id, skip, limit)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("user.create")),
) -> UserRead:
    return UserService(db).create(current_user.tenant_id, data, current_user.id)
