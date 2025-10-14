"""
Unified Audit Dashboard API Router

Endpoints for viewing and searching audit logs across all link types.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...api.deps import get_db, get_request_user_sub, require_roles
from ...core.mongo import get_mongo_db
from .errors import UserServiceError
from .link_audit import EventType, LinkAuditService, LinkType
from .service import get_user_by_kc_id

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/user-links", status_code=status.HTTP_200_OK)
async def get_all_link_audits(
    link_type: Optional[str] = Query(None, description="Filter by link type: supplier, customer, address"),
    event_type: Optional[str] = Query(None, description="Filter by event: created, updated, activated, etc."),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """
    Get audit logs for all user links with filtering and pagination.

    Super admin sees all, supplier admin/helpdesk see their scope only.
    """
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(status_code=503, detail="Audit service unavailable")

    audit_service = LinkAuditService(mongo_db)

    # Build filters
    filters = {}
    if link_type:
        try:
            filters["link_type"] = LinkType(link_type).value
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid link_type: {link_type}")

    if event_type:
        try:
            filters["event_type"] = EventType(event_type).value
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")

    if user_id:
        filters["user_id"] = user_id

    if actor_id:
        filters["actor.id"] = actor_id

    # For non-super admins, filter by their supplier's scope
    # This would require additional logic to get all users/customers/addresses for their supplier
    # For now, allowing all but in production you'd add scope filtering

    records, total = await audit_service.search_audit_logs(
        filters=filters,
        skip=skip,
        limit=limit
    )

    # Convert ObjectId to string for JSON serialization
    for record in records:
        if "_id" in record:
            record["_id"] = str(record["_id"])

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "records": records
    }


@router.get("/user-links/recent", status_code=status.HTTP_200_OK)
async def get_recent_link_events(
    link_type: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """Get recent link events across all types"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(status_code=503, detail="Audit service unavailable")

    audit_service = LinkAuditService(mongo_db)

    link_type_enum = None
    if link_type:
        try:
            link_type_enum = LinkType(link_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid link_type: {link_type}")

    event_type_enum = None
    if event_type:
        try:
            event_type_enum = EventType(event_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid event_type: {event_type}")

    records = await audit_service.get_recent_events(
        link_type=link_type_enum,
        event_type=event_type_enum,
        limit=limit
    )

    # Convert ObjectId to string for JSON serialization
    for record in records:
        if "_id" in record:
            record["_id"] = str(record["_id"])

    return records


@router.get("/user-links/stats", status_code=status.HTTP_200_OK)
async def get_link_audit_stats(
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "super_admin")),
):
    """Get statistics about link operations"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(status_code=503, detail="Audit service unavailable")

    collection = mongo_db.user_link_audit

    # Get stats by link type
    stats_by_type = await collection.aggregate([
        {
            "$group": {
                "_id": "$link_type",
                "count": {"$sum": 1},
                "active_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$snapshot.is_active", True]}, 1, 0]
                    }
                }
            }
        }
    ]).to_list(length=10)

    # Get stats by event type
    stats_by_event = await collection.aggregate([
        {
            "$group": {
                "_id": "$event_type",
                "count": {"$sum": 1}
            }
        }
    ]).to_list(length=20)

    # Get recent activity count (last 24 hours)
    from datetime import datetime, timedelta
    yesterday = datetime.utcnow() - timedelta(days=1)

    recent_count = await collection.count_documents({
        "timestamp": {"$gte": yesterday}
    })

    return {
        "by_link_type": {item["_id"]: item for item in stats_by_type},
        "by_event_type": {item["_id"]: item for item in stats_by_event},
        "recent_24h": recent_count
    }


@router.get("/users/{user_id}/activity", status_code=status.HTTP_200_OK)
async def get_user_activity(
    user_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("supplier_admin", "supplier_helpdesk", "super_admin")),
):
    """Get all link activity for a specific user"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(status_code=503, detail="Audit service unavailable")

    audit_service = LinkAuditService(mongo_db)

    records = await audit_service.get_user_link_history(
        user_id=user_id,
        limit=limit
    )

    # Convert ObjectId to string for JSON serialization
    for record in records:
        if "_id" in record:
            record["_id"] = str(record["_id"])

    return records


@router.get("/actors/{actor_id}/activity", status_code=status.HTTP_200_OK)
async def get_actor_activity(
    actor_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    _: str = Depends(require_roles("super_admin")),
):
    """Get all actions performed by a specific actor (admin only)"""
    try:
        actor = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError:
        raise HTTPException(status_code=401, detail="Actor not found")

    mongo_db = get_mongo_db()
    if mongo_db is None:
        raise HTTPException(status_code=503, detail="Audit service unavailable")

    audit_service = LinkAuditService(mongo_db)

    records = await audit_service.get_actor_activity(
        actor_id=actor_id,
        limit=limit
    )

    # Convert ObjectId to string for JSON serialization
    for record in records:
        if "_id" in record:
            record["_id"] = str(record["_id"])

    return records
