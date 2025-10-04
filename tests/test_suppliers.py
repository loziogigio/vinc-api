from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from vic_api.core.db_base import Base
from vic_api.modules.users.models import Customer, CustomerAddress, Supplier
from vic_api.modules.suppliers.schemas import SupplierCreate, SupplierUpdate
from vic_api.modules.suppliers.service import (
    create_supplier,
    get_supplier,
    list_suppliers,
    list_suppliers_for_user,
    update_supplier,
)
from vic_api.modules.users.models import User, UserAddressLink


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with TestingSession() as session:
        yield session


def test_create_supplier_generates_slug(db_session: Session) -> None:
    payload = SupplierCreate(name="DFL S.r.l.")
    supplier = create_supplier(db_session, payload)
    assert supplier.slug == "dfl-s-r-l"
    fetched = get_supplier(db_session, supplier.id)
    assert fetched.id == supplier.id


def test_update_supplier_changes_fields(db_session: Session) -> None:
    supplier = create_supplier(
        db_session,
        SupplierCreate(name="Seed Supplier", slug="seed", legal_name="Seed"),
    )
    update_supplier(
        db_session,
        supplier.id,
        SupplierUpdate(legal_name="New Name", is_active=False),
    )
    refreshed = get_supplier(db_session, supplier.id)
    assert refreshed.legal_name == "New Name"
    assert not refreshed.is_active


def test_list_suppliers_for_user(db_session: Session) -> None:
    supplier = create_supplier(db_session, SupplierCreate(name="Supplier"))
    customer = Customer(
        id=uuid4(),
        supplier_id=supplier.id,
        erp_customer_id="C123",
        name="Customer",
    )
    address = CustomerAddress(
        id=uuid4(),
        supplier_id=supplier.id,
        erp_customer_id=customer.erp_customer_id,
        erp_address_id="A1",
        label="HQ",
    )
    user = User(
        id=uuid4(),
        email="user@example.com",
        role="reseller",
        status="active",
        auth_provider="keycloak",
        kc_user_id="kc-1",
    )
    db_session.add_all([customer, address, user])
    db_session.flush()
    db_session.add(
        UserAddressLink(user_id=user.id, customer_address_id=address.id, role="buyer")
    )
    db_session.flush()

    suppliers = list_suppliers_for_user(db_session, "kc-1")
    assert [s.id for s in suppliers] == [supplier.id]

    # ensure no suppliers when kc id mismatched
    assert list_suppliers_for_user(db_session, "kc-unknown") == []


def test_duplicate_slug_raises(db_session: Session) -> None:
    create_supplier(db_session, SupplierCreate(name="Supplier", slug="dup"))
    with pytest.raises(Exception):
        create_supplier(db_session, SupplierCreate(name="Other", slug="dup"))
