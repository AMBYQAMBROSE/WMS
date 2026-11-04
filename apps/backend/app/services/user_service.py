import uuid

from sqlalchemy import delete, false, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.core.security import hash_password
from app.models.user import Role, User, UserRole
from app.repositories.base import BaseRepository
from app.schemas.user import UserCreate, UserUpdate
from app.services.auth_service import load_permissions

# Permissions an administrator cannot remove from themselves, or they would lock themselves out of user management
SELF_LOCKOUT_PERMISSION = "user.update"


class UserService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.repo = BaseRepository(db, User)

    def list(self, skip: int = 0, limit: int = 50) -> list[User]:
        return self.repo.list(self.tenant_id, skip, limit)

    def get(self, user_id: uuid.UUID) -> User:
        user = self.repo.get(self.tenant_id, user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user

    def create(self, data: UserCreate) -> User:
        roles = self._resolve_roles(data.role_codes)
        user = User(
            tenant_id=self.tenant_id,
            created_by=self.user_id,
            updated_by=self.user_id,
            username=data.username.strip(),
            display_name=data.display_name,
            email=data.email,
            password_hash=hash_password(data.password),
        )
        self.repo.create(user)
        self._set_roles(user, roles)
        return self._reload(user)

    def update(self, user_id: uuid.UUID, data: UserUpdate) -> User:
        user = self.get(user_id)
        roles = self._resolve_roles(data.role_codes)
        if user.id == self.user_id and not data.is_active:
            raise DomainError("You cannot deactivate your own account")

        self.repo.update(
            user,
            {
                "display_name": data.display_name,
                "email": data.email,
                "is_active": data.is_active,
                "updated_by": self.user_id,
            },
        )
        self._set_roles(user, roles)
        if user.id == self.user_id and SELF_LOCKOUT_PERMISSION not in load_permissions(self.db, user.id):
            # The request-level transaction rolls back: after the error none of the change is committed
            raise DomainError("You cannot remove your own user management permission, or you could no longer manage users")
        return self._reload(user)

    def reset_password(self, user_id: uuid.UUID, password: str) -> None:
        user = self.get(user_id)
        self.repo.update(user, {"password_hash": hash_password(password), "updated_by": self.user_id})

    def _resolve_roles(self, role_codes: list[str]) -> list[Role]:
        codes = list(dict.fromkeys(role_codes))
        if not codes:
            return []
        roles = list(
            self.db.scalars(
                select(Role).where(
                    Role.tenant_id == self.tenant_id, Role.code.in_(codes), Role.is_deleted == false()
                )
            )
        )
        missing = set(codes) - {r.code for r in roles}
        if missing:
            raise DomainError(f"Roles not found: {', '.join(sorted(missing))}")
        return roles

    def _set_roles(self, user: User, roles: list[Role]) -> None:
        self.db.execute(delete(UserRole).where(UserRole.user_id == user.id))
        for role in roles:
            self.db.add(UserRole(user_id=user.id, role_id=role.id))
        self.db.flush()

    def _reload(self, user: User) -> User:
        self.db.refresh(user, attribute_names=["roles"])
        return user
