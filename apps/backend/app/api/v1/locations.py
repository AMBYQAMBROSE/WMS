import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.schemas.location import LocationCreate, LocationRead, LocationUpdate
from app.services.location_service import LocationService

router = APIRouter(route_class=TransactionalRoute, prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead])
def list_locations(
    skip: int = 0,
    limit: int = Query(default=50, ge=1, le=500),
    keyword: str | None = Query(default=None, max_length=100),
    ids: list[uuid.UUID] | None = Query(default=None, max_length=200),
    types: list[str] | None = Query(default=None),
    active_only: bool = False,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("location.read")),
) -> list[LocationRead]:
    # Dropdown search: keyword fuzzy match; ids to display already selected values (up to 200); limit capped at 500, so large master data uses search rather than loading everything
    return LocationService(db).list(current_user.tenant_id, skip, limit, keyword, ids, types, active_only)


@router.post("", response_model=LocationRead, status_code=status.HTTP_201_CREATED)
def create_location(
    data: LocationCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("location.create")),
) -> LocationRead:
    try:
        return LocationService(db).create(current_user.tenant_id, data, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/{location_id}", response_model=LocationRead)
def get_location(
    location_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("location.read")),
) -> LocationRead:
    location = LocationService(db).get(current_user.tenant_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location


@router.put("/{location_id}", response_model=LocationRead)
def update_location(
    location_id: uuid.UUID,
    data: LocationUpdate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("location.update")),
) -> LocationRead:
    service = LocationService(db)
    location = service.get(current_user.tenant_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return service.update(location, data, current_user.id)


@router.delete("/{location_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_location(
    location_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("location.delete")),
) -> None:
    service = LocationService(db)
    location = service.get(current_user.tenant_id, location_id)
    if location is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    service.delete(location)
