import uuid
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


@dataclass
class CurrentUser:
    id: uuid.UUID
    tenant_id: uuid.UUID
    permissions: set[str] = field(default_factory=set)


def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="无效或过期的登录凭证"
        ) from exc

    return CurrentUser(
        id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        permissions=set(payload.get("permissions", [])),
    )


def require_permission(code: str):
    """权限校验依赖工厂：Depends(require_permission("item.create"))。"""

    def _checker(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if code not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"缺少权限: {code}"
            )
        return current_user

    return _checker


def get_db_session(db: Session = Depends(get_db)) -> Session:
    return db
