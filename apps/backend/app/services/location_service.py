import uuid

from sqlalchemy.orm import Session

from app.models.location import Location
from app.repositories.base import BaseRepository
from app.schemas.location import LocationCreate, LocationUpdate


class LocationService:
    def __init__(self, db: Session):
        self.repo = BaseRepository(db, Location)

    def list(self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50) -> list[Location]:
        return self.repo.list(tenant_id, skip, limit)

    def get(self, tenant_id: uuid.UUID, id: uuid.UUID) -> Location | None:
        return self.repo.get(tenant_id, id)

    def create(
        self, tenant_id: uuid.UUID, data: LocationCreate, created_by: uuid.UUID
    ) -> Location:
        parent_path = ""
        if data.parent_id is not None:
            parent = self.repo.get(tenant_id, data.parent_id)
            if parent is None:
                raise ValueError("父级仓位不存在")
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
