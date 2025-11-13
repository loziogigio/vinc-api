from fastapi import APIRouter

from ...modules.customers.router import router as customers_router
from ...modules.health.router import router as health_router
from ...modules.tenants.router import router as tenants_router
from ...modules.users.router import router as users_router
from ...modules.users.audit_router import router as audit_router
from ...modules.suppliers.router import router as suppliers_router
from ...modules.public_registration.router import router as public_router
from ...modules.payments.router import router as payments_router


router = APIRouter()

# Public/basic endpoints
router.include_router(health_router, tags=["health"])  # /health

# Tenant-aware endpoints
router.include_router(tenants_router, tags=["tenants"], prefix="/tenants")
router.include_router(users_router)
router.include_router(suppliers_router)
router.include_router(customers_router)
router.include_router(public_router)
router.include_router(payments_router)

# Audit endpoints (cross-cutting concern)
router.include_router(audit_router, tags=["audit"])
