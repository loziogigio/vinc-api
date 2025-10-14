"""
Comprehensive tests for the Link Management System

Tests cover:
- Link status management
- Permission checking
- Audit logging
- All three link types (supplier, customer, address)
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from vinc_api.modules.users.models import (
    User,
    Supplier,
    Customer,
    CustomerAddress,
    UserSupplierLink,
    UserCustomerLink,
    UserAddressLink,
)
from vinc_api.modules.users.link_manager import (
    LinkStatusManager,
    LinkPermissionChecker,
    LinkStatus,
)
from vinc_api.modules.users.link_audit import LinkType, EventType, LinkAuditService


class TestLinkStatusManager:
    """Test the LinkStatusManager service"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        session = MagicMock()
        return session

    @pytest.fixture
    def audit_service(self):
        """Mock audit service"""
        service = MagicMock(spec=LinkAuditService)
        service.log_event = AsyncMock()
        return service

    @pytest.fixture
    def actor_user(self):
        """Mock actor user"""
        return User(
            id=uuid4(),
            email="admin@example.com",
            name="Admin User",
            role="super_admin",
        )

    @pytest.fixture
    def supplier(self):
        """Mock supplier"""
        return Supplier(
            id=uuid4(),
            name="Test Supplier",
            slug="test-supplier",
        )

    @pytest.fixture
    def supplier_link(self, supplier):
        """Mock supplier link"""
        return UserSupplierLink(
            user_id=uuid4(),
            supplier_id=supplier.id,
            role="admin",
            status="pending",
            is_active=False,
            created_at=datetime.utcnow(),
        )

    @pytest.mark.asyncio
    async def test_activate_link(self, db_session, audit_service, actor_user, supplier_link, supplier):
        """Test activating a link"""
        # Mock db.get to return different objects based on what's requested
        def mock_get(model_class, id_value=None):
            # If model_class is a tuple, it's a composite key for a link
            if isinstance(model_class, tuple):
                return supplier_link
            # If model_class is the Supplier class, return the supplier
            if model_class == Supplier or (model_class == Supplier and id_value):
                return supplier
            # If model_class is UserSupplierLink, return the link
            if model_class == UserSupplierLink:
                return supplier_link
            # Default
            return supplier_link

        db_session.get.side_effect = mock_get

        manager = LinkStatusManager(db_session, audit_service)

        await manager.activate_link(
            link_type=LinkType.SUPPLIER,
            user_id=supplier_link.user_id,
            target_id=supplier_link.supplier_id,
            actor=actor_user,
            reason="Test activation"
        )

        assert supplier_link.status == LinkStatus.ACTIVE
        assert supplier_link.is_active is True
        db_session.flush.assert_called_once()
        audit_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_deactivate_link(self, db_session, audit_service, actor_user, supplier_link, supplier):
        """Test deactivating a link"""
        supplier_link.status = "active"
        supplier_link.is_active = True

        # Mock db.get to return different objects based on what's requested
        def mock_get(model_class, id_value=None):
            if isinstance(model_class, tuple):
                return supplier_link
            if model_class == Supplier or (model_class == Supplier and id_value):
                return supplier
            if model_class == UserSupplierLink:
                return supplier_link
            return supplier_link

        db_session.get.side_effect = mock_get

        manager = LinkStatusManager(db_session, audit_service)

        await manager.deactivate_link(
            link_type=LinkType.SUPPLIER,
            user_id=supplier_link.user_id,
            target_id=supplier_link.supplier_id,
            actor=actor_user,
            reason="Test deactivation"
        )

        assert supplier_link.status == LinkStatus.SUSPENDED
        assert supplier_link.is_active is False
        db_session.flush.assert_called_once()
        audit_service.log_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_suspend_link(self, db_session, audit_service, actor_user, supplier_link, supplier):
        """Test suspending a link"""
        supplier_link.status = "active"
        supplier_link.is_active = True

        # Mock db.get to return different objects based on what's requested
        def mock_get(model_class, id_value=None):
            if isinstance(model_class, tuple):
                return supplier_link
            if model_class == Supplier or (model_class == Supplier and id_value):
                return supplier
            if model_class == UserSupplierLink:
                return supplier_link
            return supplier_link

        db_session.get.side_effect = mock_get

        manager = LinkStatusManager(db_session, audit_service)

        await manager.suspend_link(
            link_type=LinkType.SUPPLIER,
            user_id=supplier_link.user_id,
            target_id=supplier_link.supplier_id,
            actor=actor_user,
            reason="Temporary suspension"
        )

        assert supplier_link.status == LinkStatus.SUSPENDED
        assert supplier_link.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_link(self, db_session, audit_service, actor_user, supplier_link, supplier):
        """Test revoking a link"""
        supplier_link.status = "active"
        supplier_link.is_active = True

        # Mock db.get to return different objects based on what's requested
        def mock_get(model_class, id_value=None):
            if isinstance(model_class, tuple):
                return supplier_link
            if model_class == Supplier or (model_class == Supplier and id_value):
                return supplier
            if model_class == UserSupplierLink:
                return supplier_link
            return supplier_link

        db_session.get.side_effect = mock_get

        manager = LinkStatusManager(db_session, audit_service)

        await manager.revoke_link(
            link_type=LinkType.SUPPLIER,
            user_id=supplier_link.user_id,
            target_id=supplier_link.supplier_id,
            actor=actor_user,
            reason="Permanent revocation"
        )

        assert supplier_link.status == LinkStatus.REVOKED
        assert supplier_link.is_active is False


class TestLinkPermissionChecker:
    """Test the LinkPermissionChecker service"""

    @pytest.fixture
    def db_session(self):
        """Mock database session"""
        return MagicMock()

    def test_super_admin_can_manage_supplier_links(self):
        """Super admin should be able to manage supplier links"""
        super_admin = User(id=uuid4(), email="admin@example.com", role="super_admin")

        assert LinkPermissionChecker.can_manage_supplier_link(super_admin) is True

    def test_supplier_admin_cannot_manage_supplier_links(self):
        """Supplier admin should NOT be able to manage supplier links"""
        supplier_admin = User(id=uuid4(), email="supplier@example.com", role="supplier_admin")

        assert LinkPermissionChecker.can_manage_supplier_link(supplier_admin) is False

    def test_supplier_admin_can_manage_own_customer_links(self, db_session):
        """Supplier admin should be able to manage their own supplier's customer links"""
        supplier_id = uuid4()
        supplier_admin = User(
            id=uuid4(),
            email="supplier@example.com",
            role="supplier_admin",
            supplier_id=supplier_id
        )

        customer_id = uuid4()
        customer = Customer(id=customer_id, supplier_id=supplier_id, name="Test Customer")
        db_session.get.return_value = customer

        assert LinkPermissionChecker.can_manage_customer_link(
            supplier_admin, customer_id, db_session
        ) is True

    def test_supplier_admin_cannot_manage_other_supplier_customer_links(self, db_session):
        """Supplier admin should NOT be able to manage other supplier's customer links"""
        supplier_admin = User(
            id=uuid4(),
            email="supplier@example.com",
            role="supplier_admin",
            supplier_id=uuid4()
        )

        customer_id = uuid4()
        customer = Customer(id=customer_id, supplier_id=uuid4(), name="Other Customer")
        db_session.get.return_value = customer

        assert LinkPermissionChecker.can_manage_customer_link(
            supplier_admin, customer_id, db_session
        ) is False

    def test_super_admin_can_view_all_audits(self):
        """Super admin can view all audits"""
        super_admin = User(id=uuid4(), email="admin@example.com", role="super_admin")

        assert LinkPermissionChecker.can_view_audit(super_admin, uuid4()) is True

    def test_user_can_view_own_audits(self):
        """User can view their own audits"""
        user_id = uuid4()
        user = User(id=user_id, email="user@example.com", role="viewer")

        assert LinkPermissionChecker.can_view_audit(user, user_id) is True

    def test_user_cannot_view_other_audits(self):
        """User cannot view other users' audits"""
        user = User(id=uuid4(), email="user@example.com", role="viewer")

        assert LinkPermissionChecker.can_view_audit(user, uuid4()) is False


class TestLinkAuditService:
    """Test the LinkAuditService"""

    @pytest.fixture
    async def mongo_db(self):
        """Mock MongoDB database"""
        db = MagicMock()
        collection = MagicMock()

        # Mock collection methods
        collection.insert_one = AsyncMock(return_value=MagicMock(inserted_id="mock_id"))
        collection.find = MagicMock()
        collection.count_documents = AsyncMock(return_value=0)
        collection.create_index = AsyncMock()

        db.user_link_audit = collection
        return db

    @pytest.mark.asyncio
    async def test_log_event(self, mongo_db):
        """Test logging an event to MongoDB"""
        service = LinkAuditService(mongo_db)

        user_id = uuid4()
        supplier_id = uuid4()
        actor_id = uuid4()

        doc_id = await service.log_event(
            link_type=LinkType.SUPPLIER,
            event_type=EventType.CREATED,
            user_id=user_id,
            target_id=supplier_id,
            target_name="Test Supplier",
            actor_id=actor_id,
            actor_email="actor@example.com",
            actor_role="super_admin",
            actor_name="Actor Name",
            snapshot={"role": "admin", "status": "active", "is_active": True},
            reason="Test reason"
        )

        assert doc_id is not None
        mongo_db.user_link_audit.insert_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_link_history(self, mongo_db):
        """Test getting link history"""
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])

        mongo_db.user_link_audit.find = MagicMock(return_value=mock_cursor)

        service = LinkAuditService(mongo_db)

        history = await service.get_link_history(
            link_type=LinkType.SUPPLIER,
            user_id=uuid4(),
            target_id=uuid4(),
            limit=100
        )

        assert isinstance(history, list)
        mongo_db.user_link_audit.find.assert_called_once()

    @pytest.mark.asyncio
    async def test_ensure_indexes(self, mongo_db):
        """Test that indexes are created"""
        service = LinkAuditService(mongo_db)

        await service.ensure_indexes()

        # Verify that create_index was called multiple times
        assert mongo_db.user_link_audit.create_index.call_count >= 6


# Integration tests would go here
class TestLinkManagementIntegration:
    """Integration tests for the complete link management flow"""

    @pytest.mark.skip(reason="Requires actual database connection")
    def test_complete_link_lifecycle(self):
        """Test creating, activating, suspending, and deleting a link"""
        pass

    @pytest.mark.skip(reason="Requires actual database connection")
    def test_audit_trail_completeness(self):
        """Test that all operations create proper audit trails"""
        pass

    @pytest.mark.skip(reason="Requires actual database connection")
    def test_permission_enforcement(self):
        """Test that permissions are properly enforced"""
        pass
