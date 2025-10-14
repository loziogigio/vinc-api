"""
Address Links API Router

Endpoints for managing user-address associations.
Super admin can manage all, supplier admin/helpdesk can manage their supplier's addresses.
"""

from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...api.deps import get_db, get_request_user_sub, require_roles
from ...core.mongo import get_mongo_db
from .errors import UserServiceError
from .link_audit import LinkAuditService, LinkType
from .link_manager import LinkPermissionChecker, LinkStatusManager
from .models import CustomerAddress, User, UserAddressLink
from .service import get_user_by_kc_id

router = APIRouter(tags=["user-address-links"])


@router.get("/{user_id}/addresses", status_code=status.HTTP_200_OK)
def list_user_addresses(
    user_id: UUID,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """List all address links for a user"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    links = db.execute(
        select(UserAddressLink)
        .where(UserAddressLink.user_id == user_id)
    ).scalars().all()

    # Filter by permissions if not super admin
    if actor.role != "super_admin":
        filtered_links = []
        for link in links:
            if LinkPermissionChecker.can_manage_address_link(actor, link.customer_address_id, db):
                filtered_links.append(link)
        links = filtered_links

    return [{
        "user_id": str(link.user_id),
        "address_id": str(link.customer_address_id),
        "address_label": link.customer_address.label if link.customer_address else None,
        "role": link.role,
        "status": link.status,
        "is_active": link.is_active,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
        "notes": link.notes,
    } for link in links]


@router.get("/{user_id}/addresses/{address_id}/status", status_code=status.HTTP_200_OK)
def get_address_link_status(
    user_id: UUID,
    address_id: UUID,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """Get detailed status of an address link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    # Check permissions
    if not LinkPermissionChecker.can_manage_address_link(actor, address_id, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    link = db.get(UserAddressLink, (user_id, address_id))
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    return {
        "user_id": str(link.user_id),
        "address_id": str(link.customer_address_id),
        "address_label": link.customer_address.label if link.customer_address else None,
        "role": link.role,
        "status": link.status,
        "is_active": link.is_active,
        "created_by": str(link.created_by) if link.created_by else None,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "approved_by": str(link.approved_by) if link.approved_by else None,
        "approved_at": link.approved_at.isoformat() if link.approved_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
        "notes": link.notes,
    }


@router.post("/{user_id}/addresses/{address_id}/activate", status_code=status.HTTP_200_OK)
async def activate_address_link(
    user_id: UUID,
    address_id: UUID,
    payload: dict = Body(default={}),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """Activate an address link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    # Check permissions
    if not LinkPermissionChecker.can_manage_address_link(actor, address_id, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    mongo_db = get_mongo_db()
    audit_service = LinkAuditService(mongo_db) if mongo_db else None

    status_manager = LinkStatusManager(db, audit_service)

    try:
        await status_manager.activate_link(
            link_type=LinkType.ADDRESS,
            user_id=user_id,
            target_id=address_id,
            actor=actor,
            reason=payload.get("reason"),
            ip_address=request.client.host if request else None,
        )
        db.commit()
        return {"message": "Address link activated successfully"}
    except UserServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{user_id}/addresses/{address_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_address_link(
    user_id: UUID,
    address_id: UUID,
    payload: dict = Body(default={}),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """Deactivate an address link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    # Check permissions
    if not LinkPermissionChecker.can_manage_address_link(actor, address_id, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    mongo_db = get_mongo_db()
    audit_service = LinkAuditService(mongo_db) if mongo_db else None

    status_manager = LinkStatusManager(db, audit_service)

    try:
        await status_manager.deactivate_link(
            link_type=LinkType.ADDRESS,
            user_id=user_id,
            target_id=address_id,
            actor=actor,
            reason=payload.get("reason"),
            ip_address=request.client.host if request else None,
        )
        db.commit()
        return {"message": "Address link deactivated successfully"}
    except UserServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{user_id}/addresses/{address_id}/suspend", status_code=status.HTTP_200_OK)
async def suspend_address_link(
    user_id: UUID,
    address_id: UUID,
    payload: dict = Body(default={}),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """Suspend an address link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    # Check permissions
    if not LinkPermissionChecker.can_manage_address_link(actor, address_id, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    mongo_db = get_mongo_db()
    audit_service = LinkAuditService(mongo_db) if mongo_db else None

    status_manager = LinkStatusManager(db, audit_service)

    try:
        await status_manager.suspend_link(
            link_type=LinkType.ADDRESS,
            user_id=user_id,
            target_id=address_id,
            actor=actor,
            reason=payload.get("reason"),
            ip_address=request.client.host if request else None,
        )
        db.commit()
        return {"message": "Address link suspended successfully"}
    except UserServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{user_id}/addresses/{address_id}/audit", status_code=status.HTTP_200_OK)
async def get_address_link_audit(
    user_id: UUID,
    address_id: UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """Get audit history for an address link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    # Check permissions
    if not LinkPermissionChecker.can_manage_address_link(actor, address_id, db):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    mongo_db = get_mongo_db()
    if not mongo_db:
        raise HTTPException(status_code=503, detail="Audit service unavailable")

    audit_service = LinkAuditService(mongo_db)
    history = await audit_service.get_link_history(
        link_type=LinkType.ADDRESS,
        user_id=user_id,
        target_id=address_id,
        limit=limit
    )

    # Convert ObjectId to string for JSON serialization
    for record in history:
        if "_id" in record:
            record["_id"] = str(record["_id"])

    return history
