from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from ...core.config import get_settings
from ...core.db import get_session
from ...core.keycloak import (
    KeycloakServiceError,
    create_keycloak_user,
    get_keycloak_admin,
    send_invite,
    ensure_realm_role,
    update_user_profile,
    set_user_attributes,
)
from ...core.mongo import get_mongo_db
from ..users.service import ensure_pending_reseller
from .schemas import ResellerRegistrationRequest, ResellerRegistrationResponse


router = APIRouter(prefix="/public", tags=["public"])

_COLLECTION_NAME = "reseller_registrations"
logger = logging.getLogger(__name__)


async def _ensure_keycloak_user(payload: ResellerRegistrationRequest) -> str:
    admin = get_keycloak_admin()
    if admin is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keycloak admin client unavailable",
        )

    normalized_email = payload.email.lower()

    try:
        user_id = await run_in_threadpool(
            create_keycloak_user,
            admin,
            email=normalized_email,
            name=payload.company_name,
            temp_password=None,
            enabled=False,
        )
        await run_in_threadpool(
            update_user_profile,
            admin,
            user_id,
            email=normalized_email,
            first_name=payload.company_name,
        )
        await run_in_threadpool(ensure_realm_role, admin, user_id, "reseller")
    except KeycloakServiceError as exc:
        logger.warning("Keycloak provisioning failed for reseller %s: %s", normalized_email, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    settings = get_settings()
    attributes: Dict[str, list[str]] = {
        "registration_company": [payload.company_name],
        settings.KEYCLOAK_ROLE_ATTRIBUTE: ["reseller"],
    }
    if payload.locale:
        attributes["registration_locale"] = [payload.locale]
    if payload.phone:
        attributes["registration_phone"] = [payload.phone]
    if payload.invite_code:
        attributes["registration_invite_code"] = [payload.invite_code]
    if payload.wholesale_slug:
        attributes["registration_wholesale_slug"] = [payload.wholesale_slug]

    try:
        await run_in_threadpool(set_user_attributes, admin, user_id, attributes=attributes)
        await run_in_threadpool(send_invite, admin, user_id, actions=None, settings=settings)
    except KeycloakServiceError as exc:
        logger.warning("Keycloak update/invite failed for reseller %s: %s", normalized_email, exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return user_id


async def _store_registration(
    payload: ResellerRegistrationRequest,
    keycloak_user_id: str,
) -> ResellerRegistrationResponse:
    normalized_email = payload.email.lower()

    with get_session() as session:
        if session is None:
            logger.warning("Primary database unavailable while storing reseller %s", normalized_email)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Primary database unavailable",
            )
        ensure_pending_reseller(
            session,
            email=normalized_email,
            name=payload.company_name,
            keycloak_user_id=keycloak_user_id,
        )

    db = get_mongo_db()
    if db is None:
        logger.warning("Document database unavailable while storing reseller %s", normalized_email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Document database unavailable",
        )

    doc: Dict[str, Any] = {
        "company_name": payload.company_name,
        "email": normalized_email,
        "phone": payload.phone,
        "invite_code": payload.invite_code,
        "wholesale_slug": payload.wholesale_slug,
        "locale": payload.locale,
        "keycloak_user_id": keycloak_user_id,
        "status": "pending_review",
        "created_at": datetime.now(timezone.utc),
    }

    result = await db[_COLLECTION_NAME].insert_one(doc)

    return ResellerRegistrationResponse(
        id=str(result.inserted_id),
        keycloak_user_id=keycloak_user_id,
        status="pending_review",
        message="Request received. We will reach out within 24 hours.",
        created_at=doc["created_at"],
    )


@router.post(
    "/retailer/register",
    response_model=ResellerRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_retailer(
    payload: ResellerRegistrationRequest,
) -> ResellerRegistrationResponse:
    keycloak_user_id = await _ensure_keycloak_user(payload)
    return await _store_registration(payload, keycloak_user_id)
