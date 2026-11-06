import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.api.routing import TransactionalRoute
from app.models.user import UserPreference
from app.services.document_common import utcnow

router = APIRouter(route_class=TransactionalRoute, prefix="/me/preferences", tags=["preferences"])

MAX_BYTES = 32 * 1024
Key = Path(pattern=r"^[a-z0-9:._-]{1,100}$", description="e.g. list:grns")


class PreferenceIn(BaseModel):
    value: Any


class PreferenceRead(BaseModel):
    key: str
    # Null when never saved: the web app falls back to its defaults
    value: Any = None


@router.get("/{key}", response_model=PreferenceRead)
def get_preference(
    key: str = Key,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    row = db.get(UserPreference, (user.id, key))
    return PreferenceRead(key=key, value=json.loads(row.value) if row else None)


@router.put("/{key}", response_model=PreferenceRead)
def put_preference(
    data: PreferenceIn,
    key: str = Key,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(get_current_user),
):
    value = json.dumps(data.value, ensure_ascii=False)
    if len(value.encode()) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"Preference too large (limit {MAX_BYTES // 1024} KB)")
    row = db.get(UserPreference, (user.id, key))
    if row is None:
        db.add(UserPreference(user_id=user.id, key=key, value=value, updated_at=utcnow()))
    else:
        row.value, row.updated_at = value, utcnow()
    db.flush()
    return PreferenceRead(key=key, value=data.value)
