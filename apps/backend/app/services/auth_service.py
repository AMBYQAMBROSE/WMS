import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.models.user import RolePermission, User, UserRole


class AuthService:
    """Phase 1 假设 username 在部署内全局唯一（单租户部署为主）。
    如果一套部署内要跑多个子公司(tenant)且 username 可能重复，
    需要登录时额外传 tenant_code 来定位用户，当前不做这个假设外的处理。
    """

    def __init__(self, db: Session):
        self.db = db

    def _load_permissions(self, user_id: uuid.UUID) -> list[str]:
        stmt = (
            select(RolePermission.permission_code)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.db.scalars(stmt))

    def login(self, username: str, password: str) -> str:
        user = self.db.scalars(
            select(User).where(User.username == username, User.is_deleted.is_(False))
        ).first()
        if (
            user is None
            or user.password_hash is None
            or not verify_password(password, user.password_hash)
        ):
            raise ValueError("用户名或密码错误")
        if not user.is_active:
            raise ValueError("账号已停用")

        permissions = self._load_permissions(user.id)
        return create_access_token(user.id, user.tenant_id, permissions)
