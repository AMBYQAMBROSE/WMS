"""初始化一套新部署的基础数据，可重复执行（已存在的记录会跳过）。

用法（在 apps/backend 目录下）：
    $env:SEED_ADMIN_PASSWORD = "你的密码"; python -m scripts.seed
"""

import os

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.permission_catalog import PERMISSIONS
from app.core.security import hash_password
from app.models.document import DocNumberRule
from app.models.item import Uom
from app.services.document_common import DEFAULT_PATTERN, DEFAULT_PREFIXES
from app.models.tenant import Tenant
from app.models.user import Permission, Role, RolePermission, User, UserRole

TENANT_CODE = os.environ.get("SEED_TENANT_CODE", "DEFAULT")
TENANT_NAME = os.environ.get("SEED_TENANT_NAME", "默认公司")
ADMIN_USERNAME = os.environ.get("SEED_ADMIN_USERNAME", "admin")
DEFAULT_UOMS = [("EA", "件"), ("CTN", "箱"), ("PLT", "托")]


def main() -> None:
    admin_password = os.environ.get("SEED_ADMIN_PASSWORD")

    with SessionLocal() as db:
        tenant = db.scalars(select(Tenant).where(Tenant.code == TENANT_CODE)).first()
        if tenant is None:
            tenant = Tenant(code=TENANT_CODE, name=TENANT_NAME)
            db.add(tenant)
            db.flush()
            print(f"创建租户 {TENANT_CODE}")

        existing_codes = set(db.scalars(select(Permission.code)))
        for code, module, description in PERMISSIONS:
            if code not in existing_codes:
                db.add(Permission(code=code, module=module, description=description))
        db.flush()

        admin_role = db.scalars(
            select(Role).where(Role.tenant_id == tenant.id, Role.code == "ADMIN")
        ).first()
        if admin_role is None:
            admin_role = Role(tenant_id=tenant.id, code="ADMIN", name="系统管理员", is_system=True)
            db.add(admin_role)
            db.flush()
            print("创建角色 ADMIN")

        granted = set(
            db.scalars(
                select(RolePermission.permission_code).where(
                    RolePermission.role_id == admin_role.id
                )
            )
        )
        for code, _, _ in PERMISSIONS:
            if code not in granted:
                db.add(RolePermission(role_id=admin_role.id, permission_code=code))

        admin = db.scalars(
            select(User).where(User.tenant_id == tenant.id, User.username == ADMIN_USERNAME)
        ).first()
        if admin is None:
            if not admin_password:
                raise SystemExit("首次创建管理员需要设置环境变量 SEED_ADMIN_PASSWORD")
            admin = User(
                tenant_id=tenant.id,
                username=ADMIN_USERNAME,
                display_name="管理员",
                password_hash=hash_password(admin_password),
            )
            db.add(admin)
            db.flush()
            db.add(UserRole(user_id=admin.id, role_id=admin_role.id))
            print(f"创建管理员账号 {ADMIN_USERNAME}")

        existing_uoms = set(db.scalars(select(Uom.code).where(Uom.tenant_id == tenant.id)))
        for code, name in DEFAULT_UOMS:
            if code not in existing_uoms:
                db.add(Uom(tenant_id=tenant.id, code=code, name=name))

        existing_rules = set(
            db.scalars(select(DocNumberRule.doc_type).where(DocNumberRule.tenant_id == tenant.id))
        )
        for doc_type, prefix in DEFAULT_PREFIXES.items():
            if doc_type not in existing_rules:
                db.add(
                    DocNumberRule(
                        tenant_id=tenant.id, doc_type=doc_type, prefix=prefix, pattern=DEFAULT_PATTERN
                    )
                )

        db.commit()
        print("种子数据完成")


if __name__ == "__main__":
    main()
