from fastapi import APIRouter, Depends

from ...api.deps import get_tenant_id
from .schemas import TenantInfo
from .service import get_current_tenant


router = APIRouter()


@router.get("/me", response_model=TenantInfo)
def read_my_tenant(tenant_id: str | None = Depends(get_tenant_id)) -> TenantInfo:
    return get_current_tenant(tenant_id)

