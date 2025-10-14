from typing import Generator

from fastapi import HTTPException, Request, status

from ..core.config import Settings, get_settings
from ..core.db import get_session
from ..core.redis import get_redis
from ..core.mongo import get_mongo_db
from ..core.keycloak import get_keycloak_admin
from ..modules.permissions.service import resolve_permissions
import asyncio


# --- Role aliasing ---------------------------------------------------------
# We support new role names while keeping backward compatibility with
# existing checks. Canonical roles are compared internally; user tokens
# may carry either the legacy or the new names.

_ROLE_ALIASES: dict[str, str] = {
    # Admins
    "wholesale_admin": "wholesale_admin",
    "supplier_admin": "supplier_admin",
    "wholesaler_admin": "supplier_admin",
    # Helpdesk
    "wholesaler_helpdesk": "wholesaler_helpdesk",
    "supplier_helpdesk": "wholesaler_helpdesk",  # alias
    # Other roles kept as-is
    "super_admin": "super_admin",
    "reseller": "reseller",
    "viewer": "viewer",
    # Future-proof: accept agent_admin as distinct from agent
    "agent_admin": "agent_admin",
    "agent": "agent",
}


def _canonical_role(value: str | None) -> str | None:
    if not value:
        return None
    key = value.lower()
    return _ROLE_ALIASES.get(key, key)


def _await(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():  # pragma: no cover - unlikely in sync deps
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return asyncio.run(coro)


def _resolve_permissions_context(request: Request):
    ctx = getattr(request.state, "permissions_context", None)
    if ctx is not None:
        return ctx

    tenant_id = getattr(request.state, "active_wholesaler_id", None) or getattr(
        request.state, "tenant_id", None
    )
    kc_sub = getattr(request.state, "user_sub", None)
    if not kc_sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    from ..core.db import get_session  # local import to avoid cycle

    with get_session() as db:
        ctx = _await(resolve_permissions(db, user_key=kc_sub, active_wholesaler_id=tenant_id))

    request.state.permissions_context = ctx

    if not getattr(request.state, "effective_capabilities", None) and ctx.capabilities:
        request.state.effective_capabilities = list(ctx.capabilities)
    if not getattr(request.state, "allowed_customer_ids", None) and ctx.allowed_reseller_account_ids:
        request.state.allowed_customer_ids = list(ctx.allowed_reseller_account_ids)
    if not getattr(request.state, "allowed_address_ids", None) and ctx.allowed_address_ids:
        request.state.allowed_address_ids = list(ctx.allowed_address_ids)

    return ctx


def get_settings_dep() -> Settings:
    return get_settings()


def get_tenant_id(request: Request) -> str | None:
    return getattr(request.state, "tenant_id", None)


def get_db() -> Generator:
    with get_session() as db:
        yield db


def get_redis_dep():
    return get_redis()


def get_mongo_db_dep():
    return get_mongo_db()


def get_keycloak_admin_dep():
    return get_keycloak_admin()


def require_roles(*allowed_roles: str):
    # Normalize allowed roles using canonical mapping
    allowed = { _canonical_role(role) for role in allowed_roles }
    allowed.discard(None)

    def dependency(request: Request) -> str:
        user = getattr(request.state, "authenticated_user", None)
        # Canonicalize the user role for comparison
        role_raw = getattr(user, "role", None)
        role = _canonical_role(role_raw)
        if not role or role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )
        return role

    return dependency


def require_capabilities(*required: str):
    required_caps = {cap.strip().lower() for cap in required if cap and cap.strip()}

    def dependency(request: Request) -> list[str]:
        # Fast path: if already resolved for this request, reuse
        effective_caps: list[str] | None = getattr(request.state, "effective_capabilities", None)
        if effective_caps is None:
            ctx = _resolve_permissions_context(request)
            effective_caps = list(ctx.capabilities)
            request.state.effective_capabilities = effective_caps

        missing = required_caps - set(c.lower() for c in effective_caps)
        if missing:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return effective_caps

    return dependency


def ensure_active_wholesaler_allowed(request: Request) -> str | None:
    tenant_id = getattr(request.state, "active_wholesaler_id", None) or getattr(
        request.state, "tenant_id", None
    )
    allowed_wholesalers = [
        value.lower()
        for value in (getattr(request.state, "allowed_wholesaler_ids", []) or [])
        if isinstance(value, str)
    ]
    multi_tenant = getattr(request.state, "multi_tenant", False)

    if tenant_id and allowed_wholesalers and tenant_id.lower() not in allowed_wholesalers:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wholesaler access denied")

    if (multi_tenant or allowed_wholesalers) and tenant_id:
        _resolve_permissions_context(request)

    return tenant_id


def get_request_user_sub(request: Request) -> str:
    user = getattr(request.state, "authenticated_user", None)
    kc_user_id = getattr(user, "sub", None)
    if not kc_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing user subject",
        )
    return kc_user_id


def ensure_address_access(address_id: str, request: Request) -> str:
    allowed = getattr(request.state, "allowed_address_ids", []) or []
    if address_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Address access denied",
        )
    return address_id


def get_request_user_role(request: Request) -> str | None:
    role = getattr(request.state, "user_role", None)
    if isinstance(role, str):
        return role.lower()
    return None


def get_allowed_customer_ids(request: Request) -> list[str]:
    ids = list(getattr(request.state, "allowed_customer_ids", []) or [])
    if ids:
        return ids
    allowed_wholesalers = getattr(request.state, "allowed_wholesaler_ids", []) or []
    multi_tenant = getattr(request.state, "multi_tenant", False)
    if multi_tenant or allowed_wholesalers:
        try:
            ctx = _resolve_permissions_context(request)
            return list(ctx.allowed_reseller_account_ids)
        except Exception:
            # For supplier admins using user_supplier_link, permissions might not be in MongoDB
            # Return empty list - the endpoint will handle supplier-level access
            return []
    return ids


def get_allowed_address_ids(request: Request) -> list[str]:
    ids = list(getattr(request.state, "allowed_address_ids", []) or [])
    if ids:
        return ids
    allowed_wholesalers = getattr(request.state, "allowed_wholesaler_ids", []) or []
    multi_tenant = getattr(request.state, "multi_tenant", False)
    if multi_tenant or allowed_wholesalers:
        try:
            ctx = _resolve_permissions_context(request)
            return list(ctx.allowed_address_ids)
        except Exception:
            # For supplier admins using user_supplier_link, permissions might not be in MongoDB
            # Return empty list - the endpoint will handle supplier-level access
            return []
    return ids
