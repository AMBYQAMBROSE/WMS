from fastapi import APIRouter

from app.api.v1 import (
    adjustments,
    auth,
    business_partners,
    cycle_counts,
    extensions,
    features,
    grns,
    health,
    imports,
    integration,
    items,
    locations,
    mobile,
    picks,
    purchase_orders,
    reason_codes,
    reports,
    roles,
    sales_orders,
    shipments,
    stock,
    transfers,
    uoms,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(roles.router)
api_router.include_router(business_partners.router)
api_router.include_router(items.router)
api_router.include_router(locations.router)
api_router.include_router(uoms.router)
api_router.include_router(reason_codes.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(grns.router)
api_router.include_router(transfers.putaway_router)
api_router.include_router(transfers.move_router)
api_router.include_router(adjustments.router)
api_router.include_router(cycle_counts.router)
api_router.include_router(sales_orders.router)
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
