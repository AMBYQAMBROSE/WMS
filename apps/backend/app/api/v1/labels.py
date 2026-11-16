import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user, get_db_session, require_permission
from app.api.routing import TransactionalRoute
from app.schemas.label import (
    LABEL_FIELDS,
    ItemLabelRequest,
    LabelFieldOption,
    LabelLayout,
    LabelProfileIn,
    LabelProfileRead,
    LabelProfileUpdate,
    LocationLabelRequest,
    Purpose,
    StockLabelRequest,
)
from app.services.label_service import LabelService
from app.services.printing.labels import BUILT_IN

router = APIRouter(route_class=TransactionalRoute, tags=["labels"])

PDF = {200: {"content": {"application/pdf": {}}, "description": "PDF to print"}}


def _pdf(content: bytes, name: str) -> Response:
    # inline: the browser opens it in its PDF viewer, where it is printed with the printer's own dialog
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


def _service(db: Session, user: CurrentUser) -> LabelService:
    return LabelService(db, user.tenant_id, user.id)


@router.get("/label-profiles", response_model=list[LabelProfileRead])
def list_label_profiles(
    purpose: Purpose | None = None,
    db: Session = Depends(get_db_session),
    # Everyone who prints labels picks from these; changing them needs system.settings
    user: CurrentUser = Depends(get_current_user),
):
    return [LabelProfileRead.model_validate(p) for p in _service(db, user).list_profiles(purpose)]


@router.get("/label-profiles/fields", response_model=dict[str, list[LabelFieldOption]])
def list_label_fields(_: CurrentUser = Depends(get_current_user)):
    return {purpose: [LabelFieldOption(code=c, name=n) for c, n in fields] for purpose, fields in LABEL_FIELDS.items()}


@router.get("/label-profiles/built-in", response_model=dict[str, LabelLayout])
def built_in_layouts(_: CurrentUser = Depends(get_current_user)):
    """The layouts used while a purpose has no default profile; also the starting point for a new profile"""
    return BUILT_IN


@router.post("/label-profiles", response_model=LabelProfileRead, status_code=status.HTTP_201_CREATED)
def create_label_profile(
    data: LabelProfileIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("system.settings")),
):
    return LabelProfileRead.model_validate(_service(db, user).create_profile(data))


@router.put("/label-profiles/{profile_id}", response_model=LabelProfileRead)
def update_label_profile(
    profile_id: uuid.UUID,
    data: LabelProfileUpdate,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("system.settings")),
):
    return LabelProfileRead.model_validate(_service(db, user).update_profile(profile_id, data))


@router.delete("/label-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_label_profile(
    profile_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("system.settings")),
) -> None:
    _service(db, user).delete_profile(profile_id)


@router.post("/label-profiles/test-print", response_class=Response, responses=PDF)
def test_print(
    data: LabelLayout,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("system.settings")),
):
    return _pdf(_service(db, user).test_print(data), "label-test")


@router.post("/labels/items", response_class=Response, responses=PDF)
def print_item_labels(
    data: ItemLabelRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("item.read")),
):
    return _pdf(_service(db, user).item_labels(data), "item-labels")


@router.post("/labels/stock", response_class=Response, responses=PDF)
def print_stock_labels(
    data: StockLabelRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("grn.read")),
):
    """Stock labels for a posted receipt: item, batch, expiry and quantity in one QR code that the PDA reads"""
    return _pdf(_service(db, user).stock_labels(data), "stock-labels")


@router.post("/labels/locations", response_class=Response, responses=PDF)
def print_location_labels(
    data: LocationLabelRequest,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("location.read")),
):
    return _pdf(_service(db, user).location_labels(data), "location-labels")
