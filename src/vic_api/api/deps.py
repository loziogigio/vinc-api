from typing import Generator

from fastapi import HTTPException, Request, status

from ..core.config import Settings, get_settings
from ..core.db import get_session
from ..core.redis import get_redis
from ..core.mongo import get_mongo_db
from ..core.keycloak import get_keycloak_admin


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
    allowed = set(role.lower() for role in allowed_roles)

    def dependency(request: Request) -> str:
        user = getattr(request.state, "authenticated_user", None)
        role = getattr(user, "role", None)
        if not role or role.lower() not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden",
            )
        return role

    return dependency


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
