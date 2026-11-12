import uuid

from sqlalchemy import or_, true
from sqlalchemy.orm import Session

from app.models.business_partner import BusinessPartner
from app.repositories.base import BaseRepository, check_version
from app.schemas.business_partner import BusinessPartnerCreate, BusinessPartnerUpdate
from app.services.master_guard import check_partner_deletable


class BusinessPartnerService:
    def __init__(self, db: Session):
        self.repo = BaseRepository(db, BusinessPartner)

    def list(
        self,
        tenant_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        keyword: str | None = None,
        ids: list[uuid.UUID] | None = None,
        role: str | None = None,
        active_only: bool = False,
    ) -> list[BusinessPartner]:
        """role: supplier / customer; partners of type "both" count for either"""
        conditions = []
        if keyword := (keyword or "").strip():
            conditions.append(
                or_(BusinessPartner.code.contains(keyword, autoescape=True), BusinessPartner.name.contains(keyword, autoescape=True))
            )
        if ids:
            conditions.append(BusinessPartner.id.in_(ids))
        if role:
            conditions.append(BusinessPartner.partner_type.in_([role, "both"]))
        if active_only:
            conditions.append(BusinessPartner.is_active == true())
        return self.repo.list(tenant_id, skip, limit, *conditions)

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
        check_version(partner, data.row_version, f"Business partner {partner.code}")
        fields = data.model_dump(exclude_unset=True, exclude={"row_version"})
        fields["updated_by"] = updated_by
        return self.repo.update(partner, fields)

    def delete(self, partner: BusinessPartner) -> None:
        check_partner_deletable(self.repo.db, partner.tenant_id, partner.id, partner.code)
        self.repo.soft_delete(partner)
