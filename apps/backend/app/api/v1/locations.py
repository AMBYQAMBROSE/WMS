import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.location import LocationCreate, LocationRead, LocationUpdate
from app.services.location_service import LocationService

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get("", response_model=list[LocationRead])
def list_locations(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("location.read")),
) -> list[LocationRead]:
    return LocationService(db).list(current_user.tenant_id, skip, limit)


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该仓位")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该仓位")
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该仓位")
    service.delete(location)
