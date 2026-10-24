import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import Role, User, UserRole
from app.repositories.base import BaseRepository
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = BaseRepository(db, User)

    def list(self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[User]:
        return self.repo.list(tenant_id, skip, limit)

    def create(self, tenant_id: uuid.UUID, data: UserCreate, created_by: uuid.UUID) -> User:
        user = User(
            tenant_id=tenant_id,
            created_by=created_by,
            updated_by=created_by,
            username=data.username,
            display_name=data.display_name,
            email=data.email,
            password_hash=hash_password(data.password),
        )
        self.repo.create(user)

        if data.role_codes:
            roles = self.db.scalars(
                select(Role).where(
                    Role.tenant_id == tenant_id, Role.code.in_(data.role_codes)
                )
            ).all()
            for role in roles:
                self.db.add(UserRole(user_id=user.id, role_id=role.id))
            self.db.flush()

        return user
