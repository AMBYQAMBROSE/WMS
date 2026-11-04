import uuid

from sqlalchemy import or_, true
from sqlalchemy.orm import Session

from app.models.location import Location
from app.repositories.base import BaseRepository
from app.schemas.location import LocationCreate, LocationUpdate


class LocationService:
    def __init__(self, db: Session):
        self.repo = BaseRepository(db, Location)

    def list(
        self,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        keyword: str | None = None,
        ids: list[uuid.UUID] | None = None,
        types: list[str] | None = None,
        active_only: bool = False,
    ) -> list[Location]:
        conditions = []
        if keyword := (keyword or "").strip():
            conditions.append(or_(Location.code.contains(keyword, autoescape=True), Location.name.contains(keyword, autoescape=True)))
        if ids:
            conditions.append(Location.id.in_(ids))
        if types:
            conditions.append(Location.location_type.in_(types))
        if active_only:
            conditions.append(Location.is_active == true())
        return self.repo.list(tenant_id, skip, limit, *conditions)

    def get(self, tenant_id: uuid.UUID, id: uuid.UUID) -> Location | None:
        return self.repo.get(tenant_id, id)

    def create(
        self, tenant_id: uuid.UUID, data: LocationCreate, created_by: uuid.UUID
    ) -> Location:
        parent_path = ""
        if data.parent_id is not None:
            parent = self.repo.get(tenant_id, data.parent_id)
            if parent is None:
                raise ValueError("Parent location not found")
            parent_path = parent.path

        location = Location(
            tenant_id=tenant_id,
            created_by=created_by,
            updated_by=created_by,
            path=f"{parent_path}/{data.code}",
            **data.model_dump(),
        )
        return self.repo.create(location)

    def update(self, location: Location, data: LocationUpdate, updated_by: uuid.UUID) -> Location:
        fields = data.model_dump(exclude_unset=True)
        fields["updated_by"] = updated_by
        return self.repo.update(location, fields)

    def delete(self, location: Location) -> None:
        self.repo.soft_delete(location)
