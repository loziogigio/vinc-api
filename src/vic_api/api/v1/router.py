from fastapi import APIRouter

from ...modules.health.router import router as health_router
from ...modules.tenants.router import router as tenants_router
from ...modules.users.router import router as users_router
from ...modules.suppliers.router import router as suppliers_router


router = APIRouter()

# Public/basic endpoints
router.include_router(health_router, tags=["health"])  # /health

# Tenant-aware endpoints
router.include_router(tenants_router, tags=["tenants"], prefix="/tenants")
router.include_router(users_router)
router.include_router(suppliers_router)
