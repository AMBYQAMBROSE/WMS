from fastapi import APIRouter, Depends

from app.api.idempotency import idempotency_guard
from app.api.routing import TransactionalRoute
from app.api.v1 import (
    adjustments,
    assistant,
    attachments,
    audit,
    auth,
    business_partners,
    cart,
    cycle_counts,
    document_print,
    events,
    extensions,
    features,
    grns,
    health,
    imports,
    integration,
    items,
    labels,
    locations,
    mobile,
    picks,
    preferences,
    purchase_orders,
    reason_codes,
    reports,
    roles,
    sales_orders,
    shipments,
    stock,
    system,
    transfers,
    uoms,
    users,
)

# Every POST may carry an Idempotency-Key (app/api/idempotency.py)
api_router = APIRouter(route_class=TransactionalRoute, dependencies=[Depends(idempotency_guard)])
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(business_partners.router)
api_router.include_router(items.router)
api_router.include_router(locations.router)
api_router.include_router(labels.router)
api_router.include_router(uoms.router)
api_router.include_router(reason_codes.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(grns.router)
api_router.include_router(transfers.putaway_router)
api_router.include_router(transfers.move_router)
api_router.include_router(adjustments.router)
api_router.include_router(cycle_counts.router)
api_router.include_router(sales_orders.router)
api_router.include_router(cart.router)
api_router.include_router(picks.router)
api_router.include_router(shipments.router)
api_router.include_router(extensions.return_in_router)
api_router.include_router(extensions.return_out_router)
api_router.include_router(extensions.repack_router)
api_router.include_router(extensions.asset_router)
api_router.include_router(features.router)
api_router.include_router(integration.router)
api_router.include_router(reports.router)
api_router.include_router(imports.router)
api_router.include_router(stock.router)
api_router.include_router(mobile.router)
api_router.include_router(audit.router)
api_router.include_router(system.router)
api_router.include_router(events.router)
api_router.include_router(preferences.router)
api_router.include_router(attachments.router)
api_router.include_router(document_print.router)
api_router.include_router(assistant.router)
