import uuid

from sqlalchemy.orm import Session

from app.models.business_partner import BusinessPartner
from app.repositories.base import BaseRepository
from app.schemas.business_partner import BusinessPartnerCreate, BusinessPartnerUpdate


class BusinessPartnerService:
    def __init__(self, db: Session):
        self.repo = BaseRepository(db, BusinessPartner)

    def list(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> list[BusinessPartner]:
        return self.repo.list(tenant_id, skip, limit)

    def get(self, tenant_id: uuid.UUID, id: uuid.UUID) -> BusinessPartner | None:
        return self.repo.get(tenant_id, id)

    def create(
        self, tenant_id: uuid.UUID, data: BusinessPartnerCreate, created_by: uuid.UUID
    ) -> BusinessPartner:
        partner = BusinessPartner(
            tenant_id=tenant_id,
            created_by=created_by,
            updated_by=created_by,
            **data.model_dump(),
        )
        return self.repo.create(partner)

    def update(
        self,
        partner: BusinessPartner,
        data: BusinessPartnerUpdate,
        updated_by: uuid.UUID,
    ) -> BusinessPartner:
        fields = data.model_dump(exclude_unset=True)
        fields["updated_by"] = updated_by
        return self.repo.update(partner, fields)

    def delete(self, partner: BusinessPartner) -> None:
        self.repo.soft_delete(partner)
