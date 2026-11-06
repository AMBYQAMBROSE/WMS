import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.models.user import Permission
from app.schemas.user import PermissionRead, RoleIn, RoleRead, RoleUpdate
from app.services.role_service import RoleService

router = APIRouter(route_class=TransactionalRoute, tags=["roles"])


def _service(db: Session, user: CurrentUser) -> RoleService:
    return RoleService(db, user.tenant_id, user.id)


@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(require_permission("role.read")),
):
    return list(db.scalars(select(Permission).order_by(Permission.module, Permission.code)))


@router.get("/roles", response_model=list[RoleRead])
def list_roles(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("role.read")),
):
    return _service(db, user).list()


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(
    data: RoleIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("role.create")),
):
    return _service(db, user).create(data)


@router.put("/roles/{role_id}", response_model=RoleRead)
def update_role(
    role_id: uuid.UUID,
    data: RoleUpdate,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("role.update")),
):
    return _service(db, user).update(role_id, data)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("role.delete")),
) -> None:
    _service(db, user).delete(role_id)
