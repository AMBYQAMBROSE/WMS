import uuid
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.feature_catalog import FEATURE_NAMES
from app.core.security import decode_access_token
from app.models.user import User
from app.services.auth_service import load_permissions
from app.services.document_common import is_feature_enabled

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass
class CurrentUser:
    id: uuid.UUID
    tenant_id: uuid.UUID
    username: str = ""
    display_name: str = ""
    permissions: set[str] = field(default_factory=set)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> CurrentUser:
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired login token"
        ) from exc

    # Query the database on every request: deactivations and role changes take effect immediately, without waiting for the token to expire
    user = db.get(User, user_id)
    if user is None or user.is_deleted or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is deactivated or does not exist")

    return CurrentUser(
        id=user.id,
        tenant_id=user.tenant_id,
        username=user.username,
        display_name=user.display_name,
        permissions=load_permissions(db, user.id),
    )


def require_permission(code: str):
    """Permission check dependency factory: Depends(require_permission("item.create"))."""

    def _checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if code not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing permission: {code}"
            )
        return current_user

    return _checker


def require_feature(code: str):
    """Feature flag check: modules the tenant has not enabled are rejected by the API (hiding the menu is only the UI side)"""

    def _checker(
        current_user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)
    ) -> CurrentUser:
        if not is_feature_enabled(db, current_user.tenant_id, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Feature not enabled: {FEATURE_NAMES.get(code, code)} (enable it under System > Feature flags)",
            )
        return current_user

    return _checker


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db
