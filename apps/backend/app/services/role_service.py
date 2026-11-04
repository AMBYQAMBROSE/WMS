import uuid

from sqlalchemy import delete, false, func, select
from sqlalchemy.orm import Session

from app.core.errors import DomainError, NotFoundError
from app.models.audit import record_change
from app.models.user import Permission, Role, RolePermission, UserRole
from app.schemas.user import RoleIn, RoleRead, RoleUpdate


class RoleService:
    def __init__(self, db: Session, tenant_id: uuid.UUID, user_id: uuid.UUID):
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list(self) -> list[RoleRead]:
        roles = list(
            self.db.scalars(
                select(Role)
                .where(Role.tenant_id == self.tenant_id, Role.is_deleted == false())
                .order_by(Role.is_system.desc(), Role.code)
            )
        )
        return [self._read(role) for role in roles]

    def get(self, role_id: uuid.UUID) -> RoleRead:
        return self._read(self._get(role_id))

    def create(self, data: RoleIn) -> RoleRead:
        codes = self._validate_permissions(data.permission_codes)
        role = Role(
            tenant_id=self.tenant_id,
            code=data.code.strip(),
            name=data.name,
            is_system=False,
            created_by=self.user_id,
            updated_by=self.user_id,
        )
        self.db.add(role)
        self.db.flush()
        self._set_permissions(role, codes)
        return self._read(role)

    def update(self, role_id: uuid.UUID, data: RoleUpdate) -> RoleRead:
        role = self._get(role_id)
        codes = self._validate_permissions(data.permission_codes)
        if role.is_system and set(codes) != set(self._permission_codes(role.id)):
            # The system administrator role is maintained by the seed script and always has every permission, so it can never be broken and leave nobody able to manage the system
            raise DomainError("System role permissions cannot be changed")
        role.name = data.name
        role.updated_by = self.user_id
        role.row_version += 1
        self._set_permissions(role, codes)
        return self._read(role)

    def delete(self, role_id: uuid.UUID) -> None:
        role = self._get(role_id)
        if role.is_system:
            raise DomainError("System roles cannot be deleted")
        if self._user_count(role.id):
            raise DomainError("Users still have this role; change their roles first")
        self.db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        self.db.delete(role)
        self.db.flush()

    def _get(self, role_id: uuid.UUID) -> Role:
        role = self.db.get(Role, role_id)
        if role is None or role.tenant_id != self.tenant_id or role.is_deleted:
            raise NotFoundError("Role not found")
        return role

    def _validate_permissions(self, codes: list[str]) -> list[str]:
        codes = list(dict.fromkeys(codes))
        known = set(self.db.scalars(select(Permission.code)))
        unknown = set(codes) - known
        if unknown:
            raise DomainError(f"Permissions not found: {', '.join(sorted(unknown))}")
        return codes

    def _set_permissions(self, role: Role, codes: list[str]) -> None:
        old = self._permission_codes(role.id)
        if old != sorted(codes):
            record_change(
                self.db, tenant_id=role.tenant_id, entity_type="role", entity_id=role.id, entity_label=role.code,
                changes={"permissions": [old, sorted(codes)]},
            )
        self.db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        for code in codes:
            self.db.add(RolePermission(role_id=role.id, permission_code=code))
        self.db.flush()

    def _permission_codes(self, role_id: uuid.UUID) -> list[str]:
        return sorted(
            self.db.scalars(select(RolePermission.permission_code).where(RolePermission.role_id == role_id))
        )

    def _user_count(self, role_id: uuid.UUID) -> int:
        return self.db.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)) or 0

    def _read(self, role: Role) -> RoleRead:
        return RoleRead(
            id=role.id,
            code=role.code,
            name=role.name,
            is_system=role.is_system,
            permission_codes=self._permission_codes(role.id),
            user_count=self._user_count(role.id),
        )
