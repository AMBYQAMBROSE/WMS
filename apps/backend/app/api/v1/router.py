from fastapi import APIRouter

from app.api.v1 import auth, business_partners, health, items, locations, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(business_partners.router)
api_router.include_router(items.router)
api_router.include_router(locations.router)
