"""Phase 5 extension modules: returns, repack, returnable assets. Every endpoint requires the matching feature flag to be enabled."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_feature, require_permission
from app.api.filters import document_filters
from app.api.routing import TransactionalRoute
from app.core.feature_catalog import FEATURE_REPACK, FEATURE_RETURNABLE_ASSET, FEATURE_RETURNS
from app.schemas.document import DocumentRead, DocumentSummary
from app.schemas.extension import (
    AssetBalanceRow,
    AssetTxnIn,
    AssetTxnRead,
    AssetTypeIn,
    AssetTypeRead,
    RepackIn,
    ReturnInIn,
    ReturnOutIn,
)
from app.services.repack_service import RepackService
from app.services.return_service import ReturnInService, ReturnOutService
from app.services.returnable_asset_service import ReturnableAssetService


def _document_router(prefix: str, tag: str, feature: str, permission: str, service_cls, payload_cls) -> APIRouter:
    """Customer returns, returns to supplier and repacks share the same API shape: list/create/detail/post/cancel"""
    router = APIRouter(route_class=TransactionalRoute, prefix=prefix, tags=[tag], dependencies=[Depends(require_feature(feature))])

    def service(db: Session, user: CurrentUser):
        return service_cls(db, user.tenant_id, user.id)

    @router.get("", response_model=list[DocumentSummary])
    def list_documents(
        filters: dict = Depends(document_filters),
        ref_document_id: uuid.UUID | None = None,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.read")),
    ):
        return service(db, user).list(**filters, ref_document_id=ref_document_id)

    @router.post("", response_model=DocumentRead, status_code=status.HTTP_201_CREATED)
    def create_document(
        data: payload_cls,  # type: ignore[valid-type]
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.create")),
    ):
        return service(db, user).create(data)

    @router.get("/{document_id}", response_model=DocumentRead)
    def get_document(
        document_id: uuid.UUID,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.read")),
    ):
        return service(db, user).get(document_id)

    @router.post("/{document_id}/post", response_model=DocumentRead)
    def post_document(
        document_id: uuid.UUID,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.post")),
    ):
        return service(db, user).post(document_id)

    @router.post("/{document_id}/cancel", response_model=DocumentRead)
    def cancel_document(
        document_id: uuid.UUID,
        db: Session = Depends(get_db_session),
        user: CurrentUser = Depends(require_permission(f"{permission}.cancel")),
    ):
        return service(db, user).cancel(document_id)

    return router


return_in_router = _document_router("/returns-in", "returns-in", FEATURE_RETURNS, "return_in", ReturnInService, ReturnInIn)
return_out_router = _document_router("/returns-out", "returns-out", FEATURE_RETURNS, "return_out", ReturnOutService, ReturnOutIn)
repack_router = _document_router("/repacks", "repacks", FEATURE_REPACK, "repack", RepackService, RepackIn)


asset_router = APIRouter(
    route_class=TransactionalRoute,
    prefix="/returnable-assets",
    tags=["returnable-assets"],
    dependencies=[Depends(require_feature(FEATURE_RETURNABLE_ASSET))],
)


def _assets(db: Session, user: CurrentUser) -> ReturnableAssetService:
    return ReturnableAssetService(db, user.tenant_id, user.id)


@asset_router.get("/types", response_model=list[AssetTypeRead])
def list_asset_types(
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("returnable_asset.read")),
):
    return _assets(db, user).list_types()


@asset_router.post("/types", response_model=AssetTypeRead, status_code=status.HTTP_201_CREATED)
def create_asset_type(
    data: AssetTypeIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("returnable_asset.manage")),
):
    return _assets(db, user).create_type(data)


@asset_router.get("/transactions", response_model=list[AssetTxnRead])
def list_asset_txns(
    partner_id: uuid.UUID | None = None,
    asset_type_id: uuid.UUID | None = None,
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("returnable_asset.read")),
):
    return _assets(db, user).list_txns(partner_id, asset_type_id, limit)


@asset_router.post("/transactions", response_model=AssetTxnRead, status_code=status.HTTP_201_CREATED)
def record_asset_txn(
    data: AssetTxnIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("returnable_asset.manage")),
):
    return _assets(db, user).record(data)


@asset_router.get("/balances", response_model=list[AssetBalanceRow])
def asset_balances(
    partner_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("returnable_asset.read")),
):
    return _assets(db, user).balances(partner_id)
