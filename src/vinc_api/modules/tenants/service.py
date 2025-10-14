from __future__ import annotations

from .schemas import TenantInfo


def get_current_tenant(tenant_id: str | None) -> TenantInfo:
    # In a real app, you might validate the tenant ID,
    # load tenant config/limits, or enforce isolation here.
    return TenantInfo(tenant_id=tenant_id)

