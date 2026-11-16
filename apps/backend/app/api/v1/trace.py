import csv
import io
import uuid
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_db_session, require_permission
from app.api.filters import document_filters
from app.api.routing import TransactionalRoute
from app.schemas.document import DocumentSummary
from app.schemas.trace import (
    BatchHit,
    BatchTrace,
    DocumentTrace,
    MapActivityPage,
    MapBinDetail,
    RecallIn,
    RecallRead,
    WarehouseMap,
)
from app.services.recall_service import RecallService
from app.services.trace_service import TraceService
from app.services.warehouse_map_service import MAX_EVENTS, WarehouseMapService

map_router = APIRouter(route_class=TransactionalRoute, prefix="/stock/map", tags=["warehouse map"])
trace_router = APIRouter(route_class=TransactionalRoute, prefix="/trace", tags=["traceability"])
recall_router = APIRouter(route_class=TransactionalRoute, prefix="/recalls", tags=["recalls"])


# ------------------------------------------------------------------ warehouse map


@map_router.get("", response_model=WarehouseMap)
def warehouse_map(
    warehouse_id: uuid.UUID | None = Query(default=None, description="Defaults to the first warehouse by code"),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    """Every location of one warehouse as a tree, with stock, allocation, nearest expiry, locks, counts, recalls and pick frequency"""
    return WarehouseMapService(db, user.tenant_id).map(warehouse_id)


@map_router.get("/activity", response_model=MapActivityPage)
def warehouse_activity(
    warehouse_id: uuid.UUID | None = None,
    since: datetime | None = Query(default=None, description="UTC; defaults to 15 minutes before until"),
    until: datetime | None = Query(default=None, description="UTC; defaults to now. At most 2 days after since"),
    limit: int = Query(default=MAX_EVENTS, ge=1, le=MAX_EVENTS),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    """Stock movements and PDA confirmations in the warehouse, oldest first (the newest `limit` when there are more)"""
    return WarehouseMapService(db, user.tenant_id).activity(warehouse_id, since, until, limit=limit)


@map_router.get("/locations/{location_id}", response_model=MapBinDetail)
def warehouse_map_location(
    location_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    return WarehouseMapService(db, user.tenant_id).bin_detail(location_id)


# ------------------------------------------------------------------ traceability


@trace_router.get("/batches", response_model=list[BatchHit])
def search_batches(
    q: str | None = Query(default=None, max_length=50, description="Start of the batch number"),
    item_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    return TraceService(db, user.tenant_id).search(q, item_id)


@trace_router.get("/batch", response_model=BatchTrace)
def trace_batch(
    item_id: uuid.UUID,
    batch_no: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    """Suppliers and receipts the batch came from, where it is now, and the shipments and customers it went to"""
    return TraceService(db, user.tenant_id).trace(item_id, batch_no)


@trace_router.get("/documents/lookup", response_model=DocumentTrace)
def trace_document_by_number(
    doc_no: str = Query(min_length=1, max_length=50),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    """Batches on a document found by its number (only document types the user may read)"""
    svc = TraceService(db, user.tenant_id)
    return svc.document(svc.find_document(doc_no, user.permissions).id, user.permissions)


@trace_router.get("/documents/{document_id}", response_model=DocumentTrace)
def trace_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("stock.read")),
):
    """Reverse trace: the batches on a document (e.g. a delivery order a customer complains about), their suppliers and spread"""
    return TraceService(db, user.tenant_id).document(document_id, user.permissions)


# ------------------------------------------------------------------ recalls


@recall_router.get("", response_model=list[DocumentSummary])
def list_recalls(
    filters: dict = Depends(document_filters),
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recall.read")),
):
    return RecallService(db, user.tenant_id, user.id).list(**filters)


@recall_router.post("", response_model=RecallRead, status_code=status.HTTP_201_CREATED)
def create_recall(
    data: RecallIn,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recall.create")),
):
    """Holds the batch at once (no allocation, no shipping) and, with a quarantine location, drafts the move there"""
    return RecallService(db, user.tenant_id, user.id).create(data)


@recall_router.get("/{recall_id}", response_model=RecallRead)
def get_recall(
    recall_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recall.read")),
):
    return RecallService(db, user.tenant_id, user.id).detail(recall_id)


@recall_router.post("/{recall_id}/release", response_model=RecallRead)
def release_recall(
    recall_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recall.close")),
):
    return RecallService(db, user.tenant_id, user.id).release(recall_id)


CUSTOMER_COLUMNS = [
    ("Customer code", "customer_code"), ("Customer", "customer_name"), ("Contact", "contact_name"),
    ("Phone", "contact_phone"), ("Address", "address"), ("Delivery order", "shipment_no"),
    ("Sales order", "sales_order_no"), ("Shipped at (UTC)", "shipped_at"), ("SKU", "sku_code"), ("Item", "item_name"),
    ("Batch", "batch_no"), ("Quantity", "qty"), ("Unit", "unit"), ("Vehicle", "vehicle_no"),
]


@recall_router.get("/{recall_id}/customers.csv")
def recall_customers_csv(
    recall_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    user: CurrentUser = Depends(require_permission("recall.read")),
):
    """Customers to notify: one row per delivery order that took the batch out (UTF-8 CSV with BOM, opens in Excel)"""
    svc = RecallService(db, user.tenant_id, user.id)
    recall = svc.get(recall_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([title for title, _ in CUSTOMER_COLUMNS])
    for row in svc.customers(recall_id):
        writer.writerow(["" if row[key] is None else format(row[key].normalize(), "f") if key == "qty" else row[key]
                         for _, key in CUSTOMER_COLUMNS])
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(f'recall-{recall.doc_no}-customers.csv')}"},
    )
