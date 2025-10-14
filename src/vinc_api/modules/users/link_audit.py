"""
Link Audit Service - MongoDB-based audit logging for user link management

This service provides comprehensive audit trails for all user link operations
(supplier, customer, and address links) stored in MongoDB.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = object  # type: ignore
    Field = lambda **kwargs: None  # type: ignore

from motor.motor_asyncio import AsyncIOMotorDatabase


class LinkType(str, Enum):
    """Types of user links"""
    SUPPLIER = "supplier"
    CUSTOMER = "customer"
    ADDRESS = "address"


class EventType(str, Enum):
    """Types of events that can occur on links"""
    CREATED = "created"
    UPDATED = "updated"
    ACTIVATED = "activated"
    DEACTIVATED = "deactivated"
    SUSPENDED = "suspended"
    REVOKED = "revoked"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELETED = "deleted"


class ChangeRecord(BaseModel):
    """Record of a single field change"""
    field: str
    old_value: Any
    new_value: Any


class ActorInfo(BaseModel):
    """Information about who performed the action"""
    id: str
    email: str
    role: str
    name: Optional[str] = None


class LinkSnapshot(BaseModel):
    """Snapshot of link state"""
    role: str
    status: str
    is_active: bool
    notes: Optional[str] = None


class LinkAuditRecord(BaseModel):
    """Complete audit record for a link event"""
    link_type: LinkType
    link_id: str  # Format: "user_id:target_id"
    user_id: str
    target_id: str
    target_name: str

    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    actor: ActorInfo
    changes: List[ChangeRecord] = Field(default_factory=list)

    reason: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    snapshot: LinkSnapshot
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LinkAuditService:
    """Service for logging and querying link audit records in MongoDB"""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.user_link_audit

    async def ensure_indexes(self):
        """Create indexes for efficient querying"""
        await self.collection.create_index([("user_id", 1), ("link_type", 1)])
        await self.collection.create_index([("target_id", 1), ("link_type", 1)])
        await self.collection.create_index([("actor.id", 1)])
        await self.collection.create_index([("timestamp", -1)])
        await self.collection.create_index([("event_type", 1)])
        await self.collection.create_index([("link_type", 1), ("status", 1)])
        await self.collection.create_index([
            ("link_type", 1),
            ("user_id", 1),
            ("timestamp", -1)
        ])

    async def log_event(
        self,
        link_type: LinkType,
        event_type: EventType,
        user_id: UUID,
        target_id: UUID,
        target_name: str,
        actor_id: UUID,
        actor_email: str,
        actor_role: str,
        actor_name: Optional[str],
        snapshot: Dict[str, Any],
        changes: Optional[List[Dict[str, Any]]] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        **metadata
    ) -> str:
        """
        Log a link event to MongoDB

        Returns:
            The MongoDB document ID
        """
        link_id = f"{user_id}:{target_id}"

        record = LinkAuditRecord(
            link_type=link_type,
            link_id=link_id,
            user_id=str(user_id),
            target_id=str(target_id),
            target_name=target_name,
            event_type=event_type,
            actor=ActorInfo(
                id=str(actor_id),
                email=actor_email,
                role=actor_role,
                name=actor_name
            ),
            changes=[ChangeRecord(**c) for c in (changes or [])],
            reason=reason,
            ip_address=ip_address,
            user_agent=user_agent,
            snapshot=LinkSnapshot(**snapshot),
            metadata=metadata
        )

        result = await self.collection.insert_one(record.model_dump())
        return str(result.inserted_id)

    async def get_link_history(
        self,
        link_type: LinkType,
        user_id: UUID,
        target_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get audit history for a specific link"""
        link_id = f"{user_id}:{target_id}"

        cursor = self.collection.find({
            "link_type": link_type.value,
            "link_id": link_id
        }).sort("timestamp", -1).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_user_link_history(
        self,
        user_id: UUID,
        link_type: Optional[LinkType] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all link history for a user"""
        query = {"user_id": str(user_id)}
        if link_type:
            query["link_type"] = link_type.value

        cursor = self.collection.find(query).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_recent_events(
        self,
        link_type: Optional[LinkType] = None,
        event_type: Optional[EventType] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent events across all links"""
        query = {}
        if link_type:
            query["link_type"] = link_type.value
        if event_type:
            query["event_type"] = event_type.value

        cursor = self.collection.find(query).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_actor_activity(
        self,
        actor_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get all activity by a specific actor"""
        cursor = self.collection.find({
            "actor.id": str(actor_id)
        }).sort("timestamp", -1).limit(limit)

        return await cursor.to_list(length=limit)

    async def search_audit_logs(
        self,
        filters: Dict[str, Any],
        sort_by: str = "timestamp",
        sort_order: int = -1,
        skip: int = 0,
        limit: int = 100
    ) -> tuple[List[Dict[str, Any]], int]:
        """
        Advanced search with pagination

        Returns:
            Tuple of (records, total_count)
        """
        # Clean up filters
        query = {}
        for key, value in filters.items():
            if value is not None:
                query[key] = value

        # Get total count
        total = await self.collection.count_documents(query)

        # Get paginated results
        cursor = self.collection.find(query).sort(sort_by, sort_order).skip(skip).limit(limit)
        records = await cursor.to_list(length=limit)

        return records, total
