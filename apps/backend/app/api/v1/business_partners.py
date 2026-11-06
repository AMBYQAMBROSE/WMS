import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.schemas.business_partner import (
    BusinessPartnerCreate,
    BusinessPartnerRead,
    BusinessPartnerUpdate,
)
from app.services.business_partner_service import BusinessPartnerService

router = APIRouter(route_class=TransactionalRoute, prefix="/business-partners", tags=["business-partners"])


@router.get("", response_model=list[BusinessPartnerRead])
def list_business_partners(
    skip: int = 0,
    limit: int = Query(default=50, ge=1, le=500),
    keyword: str | None = Query(default=None, max_length=100),
    ids: list[uuid.UUID] | None = Query(default=None, max_length=200),
    role: Literal["supplier", "customer"] | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("business_partner.read")),
) -> list[BusinessPartnerRead]:
    # Dropdown search: keyword fuzzy match; ids to display already selected values (up to 200); limit capped at 500, so large master data uses search rather than loading everything
    return BusinessPartnerService(db).list(current_user.tenant_id, skip, limit, keyword, ids, role, active_only)


@router.post("", response_model=BusinessPartnerRead, status_code=status.HTTP_201_CREATED)
def create_business_partner(
    data: BusinessPartnerCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("business_partner.create")),
) -> BusinessPartnerRead:
    return BusinessPartnerService(db).create(current_user.tenant_id, data, current_user.id)


@router.get("/{partner_id}", response_model=BusinessPartnerRead)
def get_business_partner(
    partner_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("business_partner.read")),
) -> BusinessPartnerRead:
    partner = BusinessPartnerService(db).get(current_user.tenant_id, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business partner not found")
    return partner


@router.put("/{partner_id}", response_model=BusinessPartnerRead)
def update_business_partner(
    partner_id: uuid.UUID,
    data: BusinessPartnerUpdate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("business_partner.update")),
) -> BusinessPartnerRead:
    service = BusinessPartnerService(db)
    partner = service.get(current_user.tenant_id, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business partner not found")
    return service.update(partner, data, current_user.id)


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_business_partner(
    partner_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("business_partner.delete")),
) -> None:
    service = BusinessPartnerService(db)
    partner = service.get(current_user.tenant_id, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business partner not found")
    service.delete(partner)
