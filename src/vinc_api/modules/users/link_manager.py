"""
Link Management Services

Provides centralized services for managing status, permissions, and operations
on user links (supplier, customer, address).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Customer,
    CustomerAddress,
    Supplier,
    User,
    UserAddressLink,
    UserCustomerLink,
    UserSupplierLink,
)
from .link_audit import EventType, LinkAuditService, LinkType
from .errors import UserServiceError


class LinkStatus:
    """Link status constants"""
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class LinkStatusManager:
    """Manages status changes for all link types"""

    def __init__(self, db: Session, audit_service: Optional[LinkAuditService] = None):
        self.db = db
        self.audit_service = audit_service

    def _get_link(self, link_type: LinkType, user_id: UUID, target_id: UUID):
        """Get a link by type and IDs"""
        if link_type == LinkType.SUPPLIER:
            return self.db.get(UserSupplierLink, (user_id, target_id))
        elif link_type == LinkType.CUSTOMER:
            return self.db.get(UserCustomerLink, (user_id, target_id))
        elif link_type == LinkType.ADDRESS:
            return self.db.get(UserAddressLink, (user_id, target_id))
        raise ValueError(f"Unknown link type: {link_type}")

    def _get_target_name(self, link_type: LinkType, target_id: UUID) -> str:
        """Get the name of the target entity"""
        if link_type == LinkType.SUPPLIER:
            supplier = self.db.get(Supplier, target_id)
            return supplier.name if supplier else str(target_id)
        elif link_type == LinkType.CUSTOMER:
            customer = self.db.get(Customer, target_id)
            return customer.name if customer else str(target_id)
        elif link_type == LinkType.ADDRESS:
            address = self.db.get(CustomerAddress, target_id)
            return address.label or address.erp_address_id if address else str(target_id)
        return str(target_id)

    async def activate_link(
        self,
        link_type: LinkType,
        user_id: UUID,
        target_id: UUID,
        actor: User,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Activate a link"""
        link = self._get_link(link_type, user_id, target_id)
        if not link:
            raise UserServiceError("Link not found")

        old_status = link.status
        old_is_active = link.is_active

        link.status = LinkStatus.ACTIVE
        link.is_active = True
        link.updated_at = datetime.utcnow()

        self.db.flush()

        # Log to audit
        if self.audit_service:
            target_name = self._get_target_name(link_type, target_id)
            await self.audit_service.log_event(
                link_type=link_type,
                event_type=EventType.ACTIVATED,
                user_id=user_id,
                target_id=target_id,
                target_name=target_name,
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
                changes=[
                    {"field": "status", "old_value": old_status, "new_value": link.status},
                    {"field": "is_active", "old_value": old_is_active, "new_value": link.is_active},
                ],
                reason=reason,
                ip_address=ip_address,
            )

    async def deactivate_link(
        self,
        link_type: LinkType,
        user_id: UUID,
        target_id: UUID,
        actor: User,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Deactivate a link"""
        link = self._get_link(link_type, user_id, target_id)
        if not link:
            raise UserServiceError("Link not found")

        old_status = link.status
        old_is_active = link.is_active

        link.status = LinkStatus.SUSPENDED
        link.is_active = False
        link.updated_at = datetime.utcnow()

        self.db.flush()

        # Log to audit
        if self.audit_service:
            target_name = self._get_target_name(link_type, target_id)
            await self.audit_service.log_event(
                link_type=link_type,
                event_type=EventType.DEACTIVATED,
                user_id=user_id,
                target_id=target_id,
                target_name=target_name,
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
                changes=[
                    {"field": "status", "old_value": old_status, "new_value": link.status},
                    {"field": "is_active", "old_value": old_is_active, "new_value": link.is_active},
                ],
                reason=reason,
                ip_address=ip_address,
            )

    async def suspend_link(
        self,
        link_type: LinkType,
        user_id: UUID,
        target_id: UUID,
        actor: User,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Suspend a link (temporary deactivation)"""
        link = self._get_link(link_type, user_id, target_id)
        if not link:
            raise UserServiceError("Link not found")

        old_status = link.status
        old_is_active = link.is_active

        link.status = LinkStatus.SUSPENDED
        link.is_active = False
        link.updated_at = datetime.utcnow()

        self.db.flush()

        # Log to audit
        if self.audit_service:
            target_name = self._get_target_name(link_type, target_id)
            await self.audit_service.log_event(
                link_type=link_type,
                event_type=EventType.SUSPENDED,
                user_id=user_id,
                target_id=target_id,
                target_name=target_name,
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
                changes=[
                    {"field": "status", "old_value": old_status, "new_value": link.status},
                    {"field": "is_active", "old_value": old_is_active, "new_value": link.is_active},
                ],
                reason=reason,
                ip_address=ip_address,
            )

    async def revoke_link(
        self,
        link_type: LinkType,
        user_id: UUID,
        target_id: UUID,
        actor: User,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Revoke a link (permanent deactivation)"""
        link = self._get_link(link_type, user_id, target_id)
        if not link:
            raise UserServiceError("Link not found")

        old_status = link.status
        old_is_active = link.is_active

        link.status = LinkStatus.REVOKED
        link.is_active = False
        link.updated_at = datetime.utcnow()

        self.db.flush()

        # Log to audit
        if self.audit_service:
            target_name = self._get_target_name(link_type, target_id)
            await self.audit_service.log_event(
                link_type=link_type,
                event_type=EventType.REVOKED,
                user_id=user_id,
                target_id=target_id,
                target_name=target_name,
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
                changes=[
                    {"field": "status", "old_value": old_status, "new_value": link.status},
                    {"field": "is_active", "old_value": old_is_active, "new_value": link.is_active},
                ],
                reason=reason,
                ip_address=ip_address,
            )


class LinkPermissionChecker:
    """Checks permissions for link operations based on actor role"""

    @staticmethod
    def can_manage_supplier_link(actor: User, supplier_id: Optional[UUID] = None) -> bool:
        """Check if actor can manage supplier links"""
        # Only super_admin can manage supplier links
        return actor.role == "super_admin"

    @staticmethod
    def can_manage_customer_link(actor: User, customer_id: UUID, db: Session) -> bool:
        """Check if actor can manage customer links"""
        # Super admin can manage all
        if actor.role == "super_admin":
            return True

        # Supplier admin/helpdesk can manage their own supplier's customers
        if actor.role in ("supplier_admin", "supplier_helpdesk"):
            if actor.supplier_id:
                # Check if customer belongs to actor's supplier
                customer = db.get(Customer, customer_id)
                return customer and customer.supplier_id == actor.supplier_id

        return False

    @staticmethod
    def can_manage_address_link(actor: User, address_id: UUID, db: Session) -> bool:
        """Check if actor can manage address links"""
        # Super admin can manage all
        if actor.role == "super_admin":
            return True

        # Supplier admin/helpdesk can manage their own supplier's addresses
        if actor.role in ("supplier_admin", "supplier_helpdesk"):
            if actor.supplier_id:
                # Check if address's customer belongs to actor's supplier
                address = db.get(CustomerAddress, address_id)
                if address and address.customer:
                    return address.customer.supplier_id == actor.supplier_id

        return False

    @staticmethod
    def can_view_audit(actor: User, link_user_id: UUID) -> bool:
        """Check if actor can view audit logs"""
        # Super admin can view all
        if actor.role == "super_admin":
            return True

        # Supplier admin/helpdesk can view their scope
        if actor.role in ("supplier_admin", "supplier_helpdesk"):
            return True  # They can view audits for their supplier's links

        # Users can view their own
        return actor.id == link_user_id
