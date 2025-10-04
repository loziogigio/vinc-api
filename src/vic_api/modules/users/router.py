from __future__ import annotations

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...api.deps import (
    get_db,
    get_keycloak_admin_dep,
    get_request_user_sub,
    get_settings_dep,
    get_redis_dep,
    require_roles,
)
from ...core.config import Settings
from .schemas import (
    UserCreatedResponse,
    UserCreateRequest,
    UserDetailResponse,
    UserMeResponse,
    UserUpdateRequest,
)
from .service import (
    UserServiceError,
    create_user,
    get_user,
    get_user_by_kc_id,
    serialize_user_created,
    serialize_user_detail,
    serialize_user_me,
    update_user,
)

# Business-facing endpoints coordinating user records and Keycloak state.
router = APIRouter(prefix="/users", tags=["users"])


# Only wholesale/super admins may provision users; Keycloak client is optional in tests.
@router.post("/", response_model=UserCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    keycloak_admin=Depends(get_keycloak_admin_dep),
    _: str = Depends(require_roles("wholesale_admin", "super_admin")),
) -> UserCreatedResponse:
    try:
        user = create_user(
            db,
            payload,
            settings=settings,
            keycloak_admin=keycloak_admin,
        )
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_created(user)


# Idempotent role/address reassignment with Keycloak attribute sync.
@router.patch("/{user_id}", response_model=UserDetailResponse)
def update_user_endpoint(
    user_id: UUID,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    keycloak_admin=Depends(get_keycloak_admin_dep),
    _: str = Depends(require_roles("wholesale_admin", "super_admin")),
) -> UserDetailResponse:
    try:
        user = update_user(
            db,
            user_id,
            payload,
            settings=settings,
            keycloak_admin=keycloak_admin,
        )
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_detail(user)


# Authenticated user context resolved via Keycloak subject header.
@router.get("/me", response_model=UserMeResponse)
def get_me_endpoint(
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    settings: Settings = Depends(get_settings_dep),
    redis=Depends(get_redis_dep),
) -> UserMeResponse:
    cache_key = f"user:me:{kc_user_id}"
    if redis is not None:
        cached = _await_redis(redis.get(cache_key))
        if cached:
            return UserMeResponse.model_validate_json(cached)

    try:
        user = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)

    response = serialize_user_me(user)

    if redis is not None:
        _await_redis(
            redis.set(
                cache_key,
                response.model_dump_json(),
                ex=settings.JWT_ME_CACHE_SECONDS,
            )
        )

    return response


def _await_redis(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():  # pragma: no cover - unlikely in sync routes
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return asyncio.run(coro)


# Administrative lookup by UUID.
@router.get("/{user_id}", response_model=UserDetailResponse)
def get_user_endpoint(user_id: UUID, db: Session = Depends(get_db)) -> UserDetailResponse:
    try:
        user = get_user(db, user_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_detail(user)
