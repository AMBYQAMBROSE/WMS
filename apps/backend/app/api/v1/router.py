from fastapi import APIRouter

from app.api.v1 import (
    auth,
    business_partners,
    grns,
    health,
    items,
    locations,
    purchase_orders,
    putaways,
    stock,
    uoms,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(business_partners.router)
api_router.include_router(items.router)
api_router.include_router(locations.router)
api_router.include_router(uoms.router)
api_router.include_router(purchase_orders.router)
api_router.include_router(grns.router)
api_router.include_router(putaways.router)
api_router.include_router(stock.router)
