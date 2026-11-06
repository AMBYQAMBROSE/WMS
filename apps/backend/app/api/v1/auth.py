import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.api.routing import TransactionalRoute
from app.api.v1.features import enabled_features
from app.schemas.auth import TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(route_class=TransactionalRoute, prefix="/auth", tags=["auth"])


class MeResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    permissions: list[str]
    features: list[str]


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db_session),
) -> TokenResponse:
    try:
        token = AuthService(db).login(form_data.username, form_data.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return TokenResponse(access_token=token)


@router.get("/me", response_model=MeResponse)
def me(
    user: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db_session)
) -> MeResponse:
    """The frontend shows/hides menus and buttons based on this; the real permission and feature flag checks still happen on every endpoint"""
    return MeResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        permissions=sorted(user.permissions),
        features=sorted(enabled_features(db, user.tenant_id)),
    )
