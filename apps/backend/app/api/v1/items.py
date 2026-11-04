import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.schemas.item import ItemCreate, ItemRead, ItemUpdate
from app.services.item_service import ItemService

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemRead])
def list_items(
    skip: int = 0,
    limit: int = Query(default=50, ge=1, le=500),
    keyword: str | None = Query(default=None, max_length=100),
    ids: list[uuid.UUID] | None = Query(default=None, max_length=200),
    active_only: bool = False,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("item.read")),
) -> list[ItemRead]:
    # Dropdown search: keyword fuzzy match; ids to display already selected values (up to 200); limit capped at 500, so large master data uses search rather than loading everything
    return ItemService(db).list(current_user.tenant_id, skip, limit, keyword, ids, active_only)


@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(
    data: ItemCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("item.create")),
) -> ItemRead:
    return ItemService(db).create(current_user.tenant_id, data, current_user.id)


@router.get("/{item_id}", response_model=ItemRead)
def get_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("item.read")),
) -> ItemRead:
    item = ItemService(db).get(current_user.tenant_id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.put("/{item_id}", response_model=ItemRead)
def update_item(
    item_id: uuid.UUID,
    data: ItemUpdate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("item.update")),
) -> ItemRead:
    service = ItemService(db)
    item = service.get(current_user.tenant_id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return service.update(item, data, current_user.id)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission("item.delete")),
) -> None:
    service = ItemService(db)
    item = service.get(current_user.tenant_id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    service.delete(item)
