"""Initialize base data for a new deployment. Safe to re-run (existing records are skipped; configuration the customer changed is not overwritten).

Usage (in apps/backend):
    $env:SEED_ADMIN_PASSWORD = "your password"; python -m scripts.seed [--preset distribution]
    python -m scripts.seed --list-presets
    python -m scripts.seed --check          # only validate all industry presets, no database connection

Industry presets (presets/*.json) define the default features, units of measure, reason codes and predefined roles; see docs/deployment.md.
"""

import argparse
import fnmatch
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.core.feature_catalog import FEATURE_CODES
from app.core.permission_catalog import PERMISSIONS
from app.core.security import hash_password
from app.models.document import DocNumberRule
from app.models.item import Uom
from app.models.reason_code import ReasonCode
from app.models.tenant import Tenant, TenantFeatureFlag
from app.models.user import Permission, Role, RolePermission, User, UserRole
from app.services.document_common import DEFAULT_PATTERN, DEFAULT_PREFIXES

PRESET_DIR = Path(__file__).resolve().parent.parent / "presets"
PERMISSION_CODES = [code for code, _, _ in PERMISSIONS]
TENANT_CODE = os.environ.get("SEED_TENANT_CODE", "DEFAULT")
TENANT_NAME = os.environ.get("SEED_TENANT_NAME", "Default company")
ADMIN_USERNAME = os.environ.get("SEED_ADMIN_USERNAME", "admin")


def _expand(patterns: list[str], where: str) -> set[str]:
    """Permissions support wildcards (*.read, grn.*); every pattern must match at least one real permission so typos do not silently do nothing"""
    codes: set[str] = set()
    for pattern in patterns:
        matched = fnmatch.filter(PERMISSION_CODES, pattern)
        if not matched:
            raise ValueError(f"{where}: permission {pattern} does not exist")
        codes.update(matched)
    return codes


def load_preset(name: str, _chain: tuple[str, ...] = ()) -> dict:
    """Load a preset and merge its "extends" parent: features are unioned, units/reasons appended by code, roles overridden by code"""
    if name in _chain:
        raise ValueError(f"Circular preset inheritance: {' -> '.join((*_chain, name))}")
    path = PRESET_DIR / f"{name}.json"
    if not path.exists():
        raise ValueError(f"Preset {name} does not exist; available: {', '.join(list_presets())}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    base = load_preset(raw["extends"], (*_chain, name)) if raw.get("extends") else {
        "features": [], "uoms": [], "reasons": {}, "roles": [],
    }

    features = sorted(set(base["features"]) | set(raw.get("features", [])))
    unknown = set(features) - FEATURE_CODES
    if unknown:
        raise ValueError(f"Preset {name}: features {', '.join(sorted(unknown))} do not exist")

    def merge_pairs(old: list, new: list) -> list:
        known = {code for code, _ in old}
        return [*old, *[(c, n) for c, n in new if c not in known]]

    reasons = dict(base["reasons"])
    for category, pairs in raw.get("reasons", {}).items():
        reasons[category] = merge_pairs(reasons.get(category, []), pairs)

    roles = {r["code"]: r for r in base["roles"]}
    for role in raw.get("roles", []):
        where = f"Preset {name} role {role['code']}"
        permissions = _expand(role["permissions"], where) - _expand(role.get("exclude", []), where)
        roles[role["code"]] = {"code": role["code"], "name": role["name"], "permissions": sorted(permissions)}

    return {
        "name": raw["name"],
        "description": raw.get("description", ""),
        "features": features,
        "uoms": merge_pairs(base["uoms"], raw.get("uoms", [])),
        "reasons": reasons,
        "roles": list(roles.values()),
    }


def list_presets() -> list[str]:
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def apply(preset: dict, admin_password: str | None) -> None:
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        tenant = db.scalars(select(Tenant).where(Tenant.code == TENANT_CODE)).first()
        if tenant is None:
            tenant = Tenant(code=TENANT_CODE, name=TENANT_NAME)
            db.add(tenant)
            db.flush()
            print(f"Created tenant {TENANT_CODE}")

        # The permission list is system-wide and owned by the code: add missing ones and keep module/description in sync
        existing = {p.code: p for p in db.scalars(select(Permission))}
        for code, module, description in PERMISSIONS:
            permission = existing.get(code)
            if permission is None:
                db.add(Permission(code=code, module=module, description=description))
            else:
                permission.module, permission.description = module, description
        db.flush()

        admin_role = db.scalars(
            select(Role).where(Role.tenant_id == tenant.id, Role.code == "ADMIN")
        ).first()
        if admin_role is None:
            admin_role = Role(tenant_id=tenant.id, code="ADMIN", name="System administrator", is_system=True)
            db.add(admin_role)
            db.flush()
            print("Created role ADMIN")

        # ADMIN always gets every permission (permissions added by an upgrade are granted here too)
        granted = set(
            db.scalars(
                select(RolePermission.permission_code).where(
                    RolePermission.role_id == admin_role.id
                )
            )
        )
        for code in PERMISSION_CODES:
            if code not in granted:
                db.add(RolePermission(role_id=admin_role.id, permission_code=code))

        admin = db.scalars(
            select(User).where(User.tenant_id == tenant.id, User.username == ADMIN_USERNAME)
        ).first()
        if admin is None:
            if not admin_password:
                raise SystemExit("Set SEED_ADMIN_PASSWORD to create the administrator the first time")
            admin = User(
                tenant_id=tenant.id,
                username=ADMIN_USERNAME,
                display_name="Administrator",
                password_hash=hash_password(admin_password),
            )
            db.add(admin)
            db.flush()
            db.add(UserRole(user_id=admin.id, role_id=admin_role.id))
            print(f"Created administrator account {ADMIN_USERNAME}")

        # Predefined roles are only created when missing; existing role permissions are maintained by the customer in the UI and not overwritten
        existing_roles = set(db.scalars(select(Role.code).where(Role.tenant_id == tenant.id)))
        for role in preset["roles"]:
            if role["code"] in existing_roles:
                continue
            new_role = Role(tenant_id=tenant.id, code=role["code"], name=role["name"])
            db.add(new_role)
            db.flush()
            for code in role["permissions"]:
                db.add(RolePermission(role_id=new_role.id, permission_code=code))
            print(f"Created role {role['code']} {role['name']} ({len(role['permissions'])} permissions)")

        # Same for feature flags: only flags never set are written from the preset, so features the customer turned off stay off
        existing_flags = set(
            db.scalars(select(TenantFeatureFlag.feature_code).where(TenantFeatureFlag.tenant_id == tenant.id))
        )
        for code in preset["features"]:
            if code not in existing_flags:
                db.add(TenantFeatureFlag(tenant_id=tenant.id, feature_code=code, is_enabled=True))
                print(f"Enabled feature {code}")

        existing_uoms = set(db.scalars(select(Uom.code).where(Uom.tenant_id == tenant.id)))
        for code, name in preset["uoms"]:
            if code not in existing_uoms:
                db.add(Uom(tenant_id=tenant.id, code=code, name=name))

        for category, defaults in preset["reasons"].items():
            existing_reasons = set(
                db.scalars(
                    select(ReasonCode.code).where(
                        ReasonCode.tenant_id == tenant.id, ReasonCode.category == category
                    )
                )
            )
            for code, name in defaults:
                if code not in existing_reasons:
                    db.add(ReasonCode(tenant_id=tenant.id, category=category, code=code, name=name))

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
        print(f"Seed data done (preset: {preset['name']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize tenant base data")
    parser.add_argument("--preset", default=os.environ.get("SEED_PRESET", "standard"), help="industry preset name")
    parser.add_argument("--list-presets", action="store_true", help="list available industry presets")
    parser.add_argument("--check", action="store_true", help="validate all presets and exit")
    args = parser.parse_args()

    try:
        if args.list_presets or args.check:
            for name in list_presets():
                preset = load_preset(name)
                print(f"{name:14} {preset['name']}: {preset['description']}")
                if args.check:
                    print(f"{'':14} features {preset['features'] or 'none'}; roles "
                          + ", ".join(f"{r['name']}({len(r['permissions'])})" for r in preset["roles"]))
            return
        preset = load_preset(args.preset)
    except ValueError as exc:
        raise SystemExit(f"Preset error: {exc}") from exc
    apply(preset, os.environ.get("SEED_ADMIN_PASSWORD"))


if __name__ == "__main__":
    main()
