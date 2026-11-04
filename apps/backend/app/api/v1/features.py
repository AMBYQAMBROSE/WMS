from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import false, select, true
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session, require_permission
from app.core.feature_catalog import FEATURE_CODES, FEATURES
from app.models.tenant import TenantFeatureFlag

router = APIRouter(prefix="/features", tags=["features"])


class FeatureRead(BaseModel):
    code: str
    name: str
    description: str
    enabled: bool


class FeatureUpdate(BaseModel):
    enabled: bool


def enabled_features(db: Session, tenant_id) -> set[str]:
    return set(
        db.scalars(
            select(TenantFeatureFlag.feature_code).where(
                TenantFeatureFlag.tenant_id == tenant_id,
                TenantFeatureFlag.is_enabled == true(),
                TenantFeatureFlag.is_deleted == false(),
            )
        )
    )


@router.get("", response_model=list[FeatureRead])
def list_features(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    enabled = enabled_features(db, user.tenant_id)
    return [
        FeatureRead(code=code, name=name, description=desc, enabled=code in enabled)
        for code, name, desc in FEATURES
    ]


@router.put("/{code}", response_model=FeatureRead)
def update_feature(
    code: str,
    data: FeatureUpdate,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("system.settings")),
):
    if code not in FEATURE_CODES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feature not found")
    flag = db.scalars(
        select(TenantFeatureFlag).where(
            TenantFeatureFlag.tenant_id == user.tenant_id, TenantFeatureFlag.feature_code == code
        )
    ).first()
    if flag is None:
        flag = TenantFeatureFlag(
            tenant_id=user.tenant_id, feature_code=code, created_by=user.id, updated_by=user.id
        )
        db.add(flag)
    flag.is_enabled = data.enabled
    flag.is_deleted = False
    flag.updated_by = user.id
    db.flush()
    name, desc = next((n, d) for c, n, d in FEATURES if c == code)
    return FeatureRead(code=code, name=name, description=desc, enabled=data.enabled)
