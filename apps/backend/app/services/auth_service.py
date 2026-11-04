import uuid

from sqlalchemy import false, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import Role, RolePermission, User, UserRole


def load_permissions(db: Session, user_id: uuid.UUID) -> set[str]:
    stmt = (
        select(RolePermission.permission_code)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id, Role.is_deleted == false())
    )
    return set(db.scalars(stmt))


class AuthService:
    """Phase 1 assumes usernames are unique within a deployment (mostly single-tenant deployments).
    If one deployment runs several subsidiaries (tenants) with possibly duplicate usernames,
    login would need a tenant_code to find the user; that case is not handled yet.
    """

    def __init__(self, db: Session):
        self.db = db

    def login(self, username: str, password: str) -> str:
        user = self.db.scalars(
            select(User).where(User.username == username, User.is_deleted == false())
        ).first()
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise ValueError("Incorrect username or password")
        if not user.is_active:
            raise ValueError("Account is deactivated")
        # Permissions are not put in the token: they are read from the database on every request, so role changes and deactivation apply immediately
        return create_access_token(user.id, user.tenant_id)
