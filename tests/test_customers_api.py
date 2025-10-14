from __future__ import annotations

from typing import Dict, Generator, Iterable
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
from vinc_api.modules.users.models import Customer, CustomerAddress, Supplier

TEST_SECRET = "customers-secret"


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

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


@pytest.fixture()
def seed_data(client: TestClient) -> Dict[str, str]:
    SessionLocal = client.app.state.test_session_local
    with SessionLocal() as session:
        supplier = Supplier(id=uuid4(), name="Supplier", slug="supplier")
        customer_one = Customer(
            id=uuid4(),
            supplier_id=supplier.id,
            erp_customer_id="CUST-001",
            name="Customer One",
            is_active=True,
        )
        customer_two = Customer(
            id=uuid4(),
            supplier_id=supplier.id,
            erp_customer_id="CUST-002",
            name="Customer Two",
            is_active=True,
        )
        address_one = CustomerAddress(
            id=uuid4(),
            customer_id=customer_one.id,
            erp_customer_id=customer_one.erp_customer_id,
            erp_address_id="ADDR-1",
            label="HQ",
            is_active=True,
        )
        address_two = CustomerAddress(
            id=uuid4(),
            customer_id=customer_two.id,
            erp_customer_id=customer_two.erp_customer_id,
            erp_address_id="ADDR-2",
            label="Warehouse",
            is_active=True,
        )
        session.add_all([supplier, customer_one, customer_two, address_one, address_two])
        session.commit()
        return {
            "supplier_id": str(supplier.id),
            "customer_one_id": str(customer_one.id),
            "customer_two_id": str(customer_two.id),
            "customer_one_address_id": str(address_one.id),
            "customer_two_address_id": str(address_two.id),
        }


def test_super_admin_can_manage_customers_and_addresses(
    client: TestClient, seed_data: Dict[str, str]
) -> None:
    admin_headers = auth_headers(role="super_admin")

    create_resp = client.post(
        "/api/v1/customers",
        json={
            "supplier_id": seed_data["supplier_id"],
            "erp_customer_id": "CUST-NEW",
            "name": "New Customer",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    customer_payload = create_resp.json()
    customer_id = customer_payload["id"]
    assert customer_payload["name"] == "New Customer"
    assert customer_payload["addresses"] == []

    update_resp = client.patch(
        f"/api/v1/customers/{customer_id}",
        json={"name": "Updated Customer"},
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["name"] == "Updated Customer"

    address_resp = client.post(
        f"/api/v1/customers/{customer_id}/addresses",
        json={
            "erp_address_id": "ADDR-NEW",
            "label": "Main Office",
            "city": "Milan",
        },
        headers=admin_headers,
    )
    assert address_resp.status_code == 201
    address_payload = address_resp.json()
    address_id = address_payload["id"]
    assert address_payload["label"] == "Main Office"

    update_address = client.patch(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        json={"label": "HQ", "is_active": False},
        headers=admin_headers,
    )
    assert update_address.status_code == 200
    assert update_address.json()["label"] == "HQ"
    assert update_address.json()["is_active"] is False

    list_addresses = client.get(
        f"/api/v1/customers/{customer_id}/addresses",
        params={"include_inactive": True},
        headers=admin_headers,
    )
    assert list_addresses.status_code == 200
    assert any(item["id"] == address_id for item in list_addresses.json())

    delete_address = client.delete(
        f"/api/v1/customers/{customer_id}/addresses/{address_id}",
        headers=admin_headers,
    )
    assert delete_address.status_code == 204

    delete_customer = client.delete(
        f"/api/v1/customers/{customer_id}",
        headers=admin_headers,
    )
    assert delete_customer.status_code == 204

    missing_resp = client.get(
        f"/api/v1/customers/{customer_id}",
        headers=admin_headers,
    )
    assert missing_resp.status_code == 404


def test_agent_sees_only_allowed_customers(
    client: TestClient, seed_data: Dict[str, str]
) -> None:
    agent_headers = auth_headers(
        role="agent",
        allowed_customers=[seed_data["customer_one_id"]],
        allowed_addresses=[seed_data["customer_one_address_id"]],
    )

    list_resp = client.get(
        "/api/v1/customers",
        headers=agent_headers,
    )
    assert list_resp.status_code == 200
    payload = list_resp.json()
    assert len(payload) == 1
    assert payload[0]["id"] == seed_data["customer_one_id"]
    assert payload[0]["addresses"]
    assert payload[0]["addresses"][0]["id"] == seed_data["customer_one_address_id"]

    detail_resp = client.get(
        f"/api/v1/customers/{seed_data['customer_one_id']}",
        headers=agent_headers,
    )
    assert detail_resp.status_code == 200
    detail_payload = detail_resp.json()
    assert detail_payload["id"] == seed_data["customer_one_id"]
    assert len(detail_payload["addresses"]) == 1

    forbidden_resp = client.get(
        f"/api/v1/customers/{seed_data['customer_two_id']}",
        headers=agent_headers,
    )
    assert forbidden_resp.status_code == 403

    addresses_resp = client.get(
        f"/api/v1/customers/{seed_data['customer_two_id']}/addresses",
        headers=agent_headers,
    )
    assert addresses_resp.status_code == 403


def test_agent_cannot_create_customer(client: TestClient, seed_data: Dict[str, str]) -> None:
    agent_headers = auth_headers(
        role="agent",
        allowed_customers=[seed_data["customer_one_id"]],
        allowed_addresses=[seed_data["customer_one_address_id"]],
    )

    create_resp = client.post(
        "/api/v1/customers",
        json={
            "supplier_id": seed_data["supplier_id"],
            "erp_customer_id": "CUST-FAIL",
            "name": "Unauthorized",
        },
        headers=agent_headers,
    )
    assert create_resp.status_code == 403


def auth_headers(
    *,
    role: str,
    sub: str | None = None,
    allowed_customers: Iterable[str] | None = None,
    allowed_addresses: Iterable[str] | None = None,
) -> Dict[str, str]:
    payload = {
        "sub": sub or f"sub-{uuid4()}",
        "role": role,
        "allowed_customers": list(allowed_customers or []),
        "allowed_addresses": list(allowed_addresses or []),
        "email": "tester@example.com",
    }
    token = jwt.encode(payload, TEST_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
