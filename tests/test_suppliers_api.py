from __future__ import annotations

from typing import Generator
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from vinc_api.app import create_app
from vinc_api.api.deps import get_db, get_keycloak_admin_dep
from vinc_api.core.config import Settings
from vinc_api.core.db_base import Base
from vinc_api.modules.users.models import Customer, CustomerAddress, Supplier, User, UserAddressLink

TEST_SECRET = "test-secret"


def auth_headers(role: str, *, sub: str | None = None, customers=None, addresses=None) -> dict[str, str]:
    payload = {
        "sub": sub or f"sub-{uuid4()}",
        "role": role,
        "allowed_customers": list(customers or []),
        "allowed_addresses": list(addresses or []),
        "email": "tester@example.com",
    }
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    settings = Settings(
        DATABASE_URL=None,
        REDIS_URL=None,
        MONGO_URL=None,
        KEYCLOAK_SERVER_URL=None,
        KEYCLOAK_REALM=None,
        KEYCLOAK_ADMIN_USERNAME=None,
        KEYCLOAK_ADMIN_PASSWORD=None,
        OTEL_ENABLED=False,
        OTEL_EXPORTER_OTLP_ENDPOINT=None,
        JWT_ENABLED=True,
        JWT_TEST_SECRET=TEST_SECRET,
    )
    app = create_app(settings=settings)
    app.state.test_session_local = SessionLocal

    def _get_db_override() -> Generator[Session, None, None]:
        session = SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_keycloak_admin_dep] = lambda: None

    with TestClient(app) as test_client:
        yield test_client


def seed_supplier(SessionLocal) -> dict[str, str]:
    with SessionLocal() as session:
        supplier = Supplier(
            id=uuid4(),
            name="Supplier",
            slug="supplier",
            status="active",
        )
        customer = Customer(
            id=uuid4(),
            supplier_id=supplier.id,
            erp_customer_id="C123",
            name="Customer",
        )
        address = CustomerAddress(
            id=uuid4(),
            customer_id=customer.id,
            erp_customer_id=customer.erp_customer_id,
            erp_address_id="A1",
            label="HQ",
        )
        user = User(
            id=uuid4(),
            email="agent@example.com",
            role="reseller",
            status="active",
            auth_provider="keycloak",
            kc_user_id="kc-agent",
        )
        session.add_all([supplier, customer, address, user])
        session.flush()
        session.add(
            UserAddressLink(
                user_id=user.id,
                customer_address_id=address.id,
                role="buyer",
            )
        )
        session.commit()
        return {
            "supplier_id": str(supplier.id),
            "customer_id": str(customer.id),
            "address_id": str(address.id),
        }


def test_super_admin_can_create_supplier(client: TestClient) -> None:
    response = client.post(
        "/api/v1/suppliers",
        json={
            "name": "DFL S.r.l.",
            "legal_email": "legal@example.com",
            "tax_id": "VAT123456",
        },
        headers=auth_headers("super_admin"),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "DFL S.r.l."
    assert body["slug"] == "dfl-s-r-l"
    assert body["status"] == "active"
    assert body["legal_email"] == "legal@example.com"
    assert body["tax_id"] == "VAT123456"


def test_supplier_me_returns_accessible_suppliers(client: TestClient) -> None:
    session_local = client.app.state.test_session_local
    seed = seed_supplier(session_local)

    response = client.get(
        "/api/v1/suppliers/me",
        headers=auth_headers(
            "agent",
            sub="kc-agent",
            customers=[seed["customer_id"]],
            addresses=[seed["address_id"]],
        ),
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == seed["supplier_id"]


def test_list_suppliers_requires_super_admin(client: TestClient) -> None:
    response = client.get(
        "/api/v1/suppliers",
        headers=auth_headers("reseller"),
    )
    assert response.status_code == 403
