"""
Supplier Links API Router

Endpoints for managing user-supplier associations (super admin only).
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...api.deps import get_db, get_request_user_sub, require_roles
from ...core.mongo import get_mongo_db
from .errors import UserServiceError
from .link_audit import LinkAuditService, LinkType
from .link_manager import LinkPermissionChecker, LinkStatusManager
from .models import Supplier, User, UserSupplierLink
from .service import get_user_by_kc_id

router = APIRouter(tags=["user-supplier-links"])


@router.get("/{user_id}/suppliers", status_code=status.HTTP_200_OK)
def list_user_suppliers(
    user_id: UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("super_admin")),
):
    """List all supplier links for a user"""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    links = db.execute(
        select(UserSupplierLink)
        .where(UserSupplierLink.user_id == user_id)
    ).scalars().all()

    return [{
        "user_id": str(link.user_id),
        "supplier_id": str(link.supplier_id),
        "supplier_name": link.supplier.name if link.supplier else None,
        "role": link.role,
        "status": link.status,
        "is_active": link.is_active,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "updated_at": link.updated_at.isoformat() if link.updated_at else None,
        "notes": link.notes,
    } for link in links]


@router.post("/{user_id}/suppliers", status_code=status.HTTP_201_CREATED)
async def create_supplier_link(
    user_id: UUID,
    payload: dict = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("super_admin")),
):
    """Create a new supplier link for a user"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    supplier_id = UUID(payload.get("supplier_id"))
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    # Check if link already exists
    existing = db.get(UserSupplierLink, (user_id, supplier_id))
    if existing:
        raise HTTPException(status_code=400, detail="Link already exists")

    # Create link
    role = payload.get("role", "viewer")
    if role not in ("admin", "helpdesk", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role")

    # Get status from payload or default to 'active'
    link_status = payload.get("status", "active")
    if link_status not in ("pending", "active", "suspended"):
        raise HTTPException(status_code=400, detail="Invalid status")

    # Get is_active from payload or default based on status
    is_active = payload.get("is_active", link_status == "active")

    link = UserSupplierLink(
        user_id=user_id,
        supplier_id=supplier_id,
        role=role,
        status=link_status,
        is_active=is_active,
        created_by=actor.id,
        notes=payload.get("notes"),
    )

    db.add(link)
    db.flush()

    # Log to audit
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        audit_service = LinkAuditService(mongo_db)
        await audit_service.log_event(
            link_type=LinkType.SUPPLIER,
            event_type="created",
            user_id=user_id,
            target_id=supplier_id,
            target_name=supplier.name,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role,
            actor_name=actor.name,
            snapshot={
                "role": link.role,
                "status": link.status,
                "is_active": link.is_active,
                "notes": link.notes,
            },
            reason=payload.get("reason"),
            ip_address=request.client.host if request else None,
        )

    db.commit()

    return {
        "user_id": str(link.user_id),
        "supplier_id": str(link.supplier_id),
        "role": link.role,
        "status": link.status,
        "is_active": link.is_active,
    }


@router.patch("/{user_id}/suppliers/{supplier_id}", status_code=status.HTTP_200_OK)
async def update_supplier_link(
    user_id: UUID,
    supplier_id: UUID,
    payload: dict = Body(...),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("super_admin")),
):
    """Update a supplier link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    link = db.get(UserSupplierLink, (user_id, supplier_id))
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    changes = []

    # Update role
    if "role" in payload:
        new_role = payload["role"]
        if new_role not in ("admin", "helpdesk", "viewer"):
            raise HTTPException(status_code=400, detail="Invalid role")
        if link.role != new_role:
            changes.append({"field": "role", "old_value": link.role, "new_value": new_role})
            link.role = new_role

    # Update status
    if "status" in payload:
        new_status = payload["status"]
        if new_status not in ("pending", "active", "suspended", "revoked"):
            raise HTTPException(status_code=400, detail="Invalid status")
        if link.status != new_status:
            changes.append({"field": "status", "old_value": link.status, "new_value": new_status})
            link.status = new_status

    # Update is_active
    if "is_active" in payload:
        new_is_active = bool(payload["is_active"])
        if link.is_active != new_is_active:
            changes.append({"field": "is_active", "old_value": link.is_active, "new_value": new_is_active})
            link.is_active = new_is_active

    # Update notes
    if "notes" in payload:
        old_notes = link.notes
        link.notes = payload["notes"]
        changes.append({"field": "notes", "old_value": old_notes, "new_value": link.notes})

    link.updated_at = None  # Will trigger onupdate
    db.flush()

    # Log to audit
    if changes:
        mongo_db = get_mongo_db()
        if mongo_db is not None:
            audit_service = LinkAuditService(mongo_db)
            supplier = link.supplier
            await audit_service.log_event(
                link_type=LinkType.SUPPLIER,
                event_type="updated",
                user_id=user_id,
                target_id=supplier_id,
                target_name=supplier.name if supplier else str(supplier_id),
                actor_id=actor.id,
                actor_email=actor.email,
                actor_role=actor.role,
                actor_name=actor.name,
                snapshot={
                    "role": link.role,
                    "status": link.status,
                    "is_active": link.is_active,
                    "notes": link.notes,
                },
                changes=changes,
                reason=payload.get("reason"),
                ip_address=request.client.host if request else None,
            )

    db.commit()

    return {
        "user_id": str(link.user_id),
        "supplier_id": str(link.supplier_id),
        "role": link.role,
        "status": link.status,
        "is_active": link.is_active,
    }


@router.delete("/{user_id}/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier_link(
    user_id: UUID,
    supplier_id: UUID,
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("super_admin")),
):
    """Delete a supplier link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    link = db.get(UserSupplierLink, (user_id, supplier_id))
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")

    supplier = link.supplier
    supplier_name = supplier.name if supplier else str(supplier_id)

    db.delete(link)
    db.flush()

    # Log to audit
    mongo_db = get_mongo_db()
    if mongo_db is not None:
        audit_service = LinkAuditService(mongo_db)
        await audit_service.log_event(
            link_type=LinkType.SUPPLIER,
            event_type="deleted",
            user_id=user_id,
            target_id=supplier_id,
            target_name=supplier_name,
            actor_id=actor.id,
            actor_email=actor.email,
            actor_role=actor.role,
            actor_name=actor.name,
            snapshot={
                "role": link.role,
                "status": link.status,
                "is_active": link.is_active,
                "notes": link.notes,
            },
            ip_address=request.client.host if request else None,
        )

    db.commit()
    return None


@router.post("/{user_id}/suppliers/{supplier_id}/activate", status_code=status.HTTP_200_OK)
async def activate_supplier_link(
    user_id: UUID,
    supplier_id: UUID,
    payload: dict = Body(default={}),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("super_admin")),
):
    """Activate a supplier link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    audit_service = LinkAuditService(mongo_db) if mongo_db else None

    status_manager = LinkStatusManager(db, audit_service)

    try:
        await status_manager.activate_link(
            link_type=LinkType.SUPPLIER,
            user_id=user_id,
            target_id=supplier_id,
            actor=actor,
            reason=payload.get("reason"),
            ip_address=request.client.host if request else None,
        )
        db.commit()
        return {"message": "Link activated successfully"}
    except UserServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{user_id}/suppliers/{supplier_id}/deactivate", status_code=status.HTTP_200_OK)
async def deactivate_supplier_link(
    user_id: UUID,
    supplier_id: UUID,
    payload: dict = Body(default={}),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("super_admin")),
):
    """Deactivate a supplier link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    audit_service = LinkAuditService(mongo_db) if mongo_db else None

    status_manager = LinkStatusManager(db, audit_service)

    try:
        await status_manager.deactivate_link(
            link_type=LinkType.SUPPLIER,
            user_id=user_id,
            target_id=supplier_id,
            actor=actor,
            reason=payload.get("reason"),
            ip_address=request.client.host if request else None,
        )
        db.commit()
        return {"message": "Link deactivated successfully"}
    except UserServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{user_id}/suppliers/{supplier_id}/suspend", status_code=status.HTTP_200_OK)
async def suspend_supplier_link(
    user_id: UUID,
    supplier_id: UUID,
    payload: dict = Body(default={}),
    request: Request = None,
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("super_admin")),
):
    """Suspend a supplier link"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    audit_service = LinkAuditService(mongo_db) if mongo_db else None

    status_manager = LinkStatusManager(db, audit_service)

    try:
        await status_manager.suspend_link(
            link_type=LinkType.SUPPLIER,
            user_id=user_id,
            target_id=supplier_id,
            actor=actor,
            reason=payload.get("reason"),
            ip_address=request.client.host if request else None,
        )
        db.commit()
        return {"message": "Link suspended successfully"}
    except UserServiceError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{user_id}/suppliers/{supplier_id}/audit", status_code=status.HTTP_200_OK)
async def get_supplier_link_audit(
    user_id: UUID,
    supplier_id: UUID,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("super_admin")),
):
    """Get audit history for a supplier link"""
    mongo_db = get_mongo_db()
    if not mongo_db:
        raise HTTPException(status_code=503, detail="Audit service unavailable")

    audit_service = LinkAuditService(mongo_db)
    history = await audit_service.get_link_history(
        link_type=LinkType.SUPPLIER,
        user_id=user_id,
        target_id=supplier_id,
        limit=limit
    )

    # Convert ObjectId to string for JSON serialization
    for record in history:
        if "_id" in record:
            record["_id"] = str(record["_id"])

    return history
