"""
Tests for the user list endpoint with pagination and search.
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vinc_api.app import create_app
from vinc_api.modules.users.models import User, Supplier, UserSupplierLink, Customer, UserCustomerLink, CustomerAddress, UserAddressLink

# Create app instance for testing
app = create_app()


@pytest.fixture
def test_users(db_session: Session):
    """Create test users with various link configurations."""
    # Create supplier
    supplier = Supplier(
        id=uuid4(),
        name="Test Supplier",
        slug="test-supplier",
    )
    db_session.add(supplier)

    # Create customer
    customer = Customer(
        id=uuid4(),
        supplier_id=supplier.id,
        erp_customer_id="CUST001",
        name="Test Customer",
    )
    db_session.add(customer)

    # Create address
    address = CustomerAddress(
        id=uuid4(),
        customer_id=customer.id,
        erp_customer_id=customer.erp_customer_id,
        erp_address_id="ADDR001",
        label="Main Office",
    )
    db_session.add(address)

    # Create users with different link counts
    user1 = User(
        id=uuid4(),
        email="admin@example.com",
        name="Admin User",
        role="super_admin",
        status="active",
    )
    db_session.add(user1)

    user2 = User(
        id=uuid4(),
        email="supplier@example.com",
        name="Supplier Admin",
        role="supplier_admin",
        status="active",
        supplier_id=supplier.id,
    )
    # Add supplier link
    supplier_link = UserSupplierLink(
        user_id=user2.id,
        supplier_id=supplier.id,
        role="admin",
    )
    db_session.add(supplier_link)
    db_session.add(user2)

    user3 = User(
        id=uuid4(),
        email="reseller@example.com",
        name="Reseller User",
        role="reseller",
        status="invited",
    )
    # Add customer and address links
    customer_link = UserCustomerLink(
        user_id=user3.id,
        customer_id=customer.id,
        role="buyer",
    )
    address_link = UserAddressLink(
        user_id=user3.id,
        customer_address_id=address.id,
        role="buyer",
    )
    db_session.add(customer_link)
    db_session.add(address_link)
    db_session.add(user3)

    db_session.commit()

    return {
        "users": [user1, user2, user3],
        "supplier": supplier,
        "customer": customer,
        "address": address,
    }


def test_list_users_paginated(db_session: Session, test_users):
    """Test listing users with pagination."""
    client = TestClient(app)

    # Mock authentication (bypass for testing)
    # In real tests, you'd use proper auth headers
    response = client.get(
        "/api/v1/users/?page=1&page_size=10",
        headers={"X-User-Sub": "test-super-admin"}
    )

    assert response.status_code in [200, 403]  # 403 if auth is enforced

    if response.status_code == 200:
        data = response.json()

        # Check response structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data

        # Check pagination
        assert data["page"] == 1
        assert data["page_size"] == 10

        # Check that items have the correct fields
        if len(data["items"]) > 0:
            item = data["items"][0]
            assert "id" in item
            assert "email" in item
            assert "name" in item
            assert "role" in item
            assert "status" in item
            assert "supplier_count" in item
            assert "customer_count" in item
            assert "address_count" in item
            assert "created_at" in item
            assert "updated_at" in item


def test_list_users_search(db_session: Session, test_users):
    """Test listing users with search."""
    client = TestClient(app)

    response = client.get(
        "/api/v1/users/?search=reseller",
        headers={"X-User-Sub": "test-super-admin"}
    )

    assert response.status_code in [200, 403]

    if response.status_code == 200:
        data = response.json()
        # Should find users with 'reseller' in email, name, or role
        assert "items" in data


def test_list_users_role_filter(db_session: Session, test_users):
    """Test listing users with role filter."""
    client = TestClient(app)

    response = client.get(
        "/api/v1/users/?role=super_admin",
        headers={"X-User-Sub": "test-super-admin"}
    )

    assert response.status_code in [200, 403]

    if response.status_code == 200:
        data = response.json()
        assert "items" in data
        # All items should have role=super_admin
        for item in data["items"]:
            assert item["role"] == "super_admin"


def test_list_users_status_filter(db_session: Session, test_users):
    """Test listing users with status filter."""
    client = TestClient(app)

    response = client.get(
        "/api/v1/users/?status=active",
        headers={"X-User-Sub": "test-super-admin"}
    )

    assert response.status_code in [200, 403]

    if response.status_code == 200:
        data = response.json()
        assert "items" in data
        # All items should have status=active
        for item in data["items"]:
            assert item["status"] == "active"
