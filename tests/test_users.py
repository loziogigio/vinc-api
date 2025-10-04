from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from vic_api.core.config import Settings
from vic_api.core.db_base import Base
from vic_api.modules.users.models import Customer, CustomerAddress, Supplier
from vic_api.modules.users.schemas import (
    CustomerSelection,
    UserCreateRequest,
    UserRole,
    UserUpdateRequest,
)
from vic_api.modules.users.service import (
    UserServiceError,
    create_user,
    serialize_user_detail,
    serialize_user_me,
    update_user,
)


@pytest.fixture()
def db_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    with TestingSession() as session:
        yield session


def make_settings() -> Settings:
    return Settings(
        DATABASE_URL=None,
        REDIS_URL=None,
        MONGO_URL=None,
        KEYCLOAK_SERVER_URL=None,
        KEYCLOAK_REALM=None,
        KEYCLOAK_ADMIN_USERNAME=None,
        KEYCLOAK_ADMIN_PASSWORD=None,
        OTEL_ENABLED=False,
        OTEL_EXPORTER_OTLP_ENDPOINT=None,
        JWT_ENABLED=False,
    )


def seed_customer(session: Session) -> tuple[Supplier, Customer, CustomerAddress]:
    suffix = uuid4().hex[:8]
    supplier = Supplier(
        id=uuid4(),
        name="Supplier",
        slug=f"supplier-{suffix}",
        is_active=True,
    )
    customer = Customer(
        id=uuid4(),
        supplier_id=supplier.id,
        erp_customer_id=f"CUST-{suffix}",
        name="Customer",
        is_active=True,
    )
    address = CustomerAddress(
        id=uuid4(),
        supplier_id=supplier.id,
        erp_customer_id=customer.erp_customer_id,
        erp_address_id=f"ADDR-{suffix}",
        label="HQ",
        pricelist_code="PL",
        channel_code="ONLINE",
        is_active=True,
    )
    session.add_all([supplier, customer, address])
    session.flush()
    return supplier, customer, address


def test_create_user_assigns_links(db_session: Session) -> None:
    settings = make_settings()
    supplier, customer, address = seed_customer(db_session)

    payload = UserCreateRequest(
        email="sales@example.com",
        name="Sales",
        role=UserRole.AGENT,
        customers=[
            CustomerSelection(
                customer_id=str(customer.id),
                all_addresses=False,
                address_ids=[str(address.id)],
            )
        ],
        send_invite=False,
    )

    user = create_user(db_session, payload, settings=settings)

    assert {link.customer_id for link in user.customer_links} == {customer.id}
    assert {link.customer_address_id for link in user.address_links} == {address.id}

    detail = serialize_user_detail(user)
    assert detail.supplier is not None and detail.supplier.id == supplier.id
    assert detail.customers[0].addresses[0].pricelist_code == "PL"


def test_create_user_with_all_addresses(db_session: Session) -> None:
    settings = make_settings()
    supplier, customer, address = seed_customer(db_session)
    second_address = CustomerAddress(
        id=uuid4(),
        supplier_id=supplier.id,
        erp_customer_id=customer.erp_customer_id,
        erp_address_id=f"ADDR-{uuid4().hex[:8]}",
        label="Branch",
        is_active=True,
    )
    db_session.add(second_address)
    db_session.flush()

    payload = UserCreateRequest(
        email="multi@example.com",
        name="Multi",
        role=UserRole.RESELLER,
        customers=[
            CustomerSelection(
                customer_id=customer.erp_customer_id,
                all_addresses=True,
            )
        ],
    )

    user = create_user(db_session, payload, settings=settings)
    assigned_addresses = {link.customer_address_id for link in user.address_links}
    assert assigned_addresses == {address.id, second_address.id}


def test_update_user_reassigns_customers(db_session: Session) -> None:
    settings = make_settings()
    supplier, customer_a, address_a = seed_customer(db_session)
    _, customer_b, address_b = seed_customer(db_session)

    payload = UserCreateRequest(
        email="user@example.com",
        name="User",
        role=UserRole.AGENT,
        customers=[
            CustomerSelection(
                customer_id=str(customer_a.id),
                address_ids=[str(address_a.id)],
            )
        ],
    )

    user = create_user(db_session, payload, settings=settings)

    update_payload = UserUpdateRequest(
        role=UserRole.SUPER_ADMIN,
        customers=[
            CustomerSelection(
                customer_id=str(customer_b.id),
                address_ids=[str(address_b.id)],
            )
        ],
    )

    updated = update_user(
        db_session,
        user.id,
        update_payload,
        settings=settings,
        keycloak_admin=None,
    )

    assert updated.role == UserRole.SUPER_ADMIN.value
    assert {link.customer_id for link in updated.customer_links} == {customer_b.id}


def test_create_user_requires_unique_email(db_session: Session) -> None:
    settings = make_settings()
    _, customer, address = seed_customer(db_session)
    payload = UserCreateRequest(
        email="dup@example.com",
        name="Dup",
        role=UserRole.AGENT,
        customers=[
            CustomerSelection(
                customer_id=str(customer.id),
                address_ids=[str(address.id)],
            )
        ],
    )
    create_user(db_session, payload, settings=settings)

    with pytest.raises(UserServiceError):
        create_user(db_session, payload, settings=settings)


def test_serialize_user_me_includes_addresses(db_session: Session) -> None:
    settings = make_settings()
    supplier, customer, address = seed_customer(db_session)

    user = create_user(
        db_session,
        UserCreateRequest(
            email="me@example.com",
            name="Self",
            role=UserRole.AGENT,
            customers=[
                CustomerSelection(
                    customer_id=str(customer.id),
                    address_ids=[str(address.id)],
                )
            ],
        ),
        settings=settings,
    )
    user.kc_user_id = "kc-123"
    db_session.flush()
    refreshed = serialize_user_me(user)
    assert refreshed.addresses[0].id == address.id
    assert refreshed.customers[0].id == customer.id
    assert refreshed.supplier and refreshed.supplier.id == supplier.id
