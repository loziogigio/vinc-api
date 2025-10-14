from __future__ import annotations

from typing import Generator, Iterable
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
from vinc_api.modules.users.models import Customer, CustomerAddress, Supplier, User


TEST_JWT_SECRET = "test-secret"


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
        JWT_TEST_SECRET=TEST_JWT_SECRET,
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
def seed_data(client: TestClient) -> dict[str, str]:
    SessionLocal = client.app.state.test_session_local
    with SessionLocal() as session:
        supplier = Supplier(
            id=uuid4(),
            name="Supplier",
            slug="supplier",
            logo_url="https://example.com/logo.png",
            is_active=True,
        )
        customer = Customer(
            id=uuid4(),
            supplier_id=supplier.id,
            erp_customer_id="ERP-CUST",
            name="Customer",
            is_active=True,
        )
        address = CustomerAddress(
            id=uuid4(),
            customer_id=customer.id,
            erp_customer_id=customer.erp_customer_id,
            erp_address_id="ADDR-001",
            label="HQ",
            pricelist_code="PL",
            channel_code="ONLINE",
            is_active=True,
        )
        session.add_all([supplier, customer, address])
        session.commit()
        return {
            "supplier_id": str(supplier.id),
            "customer_id": str(customer.id),
            "customer_erp": customer.erp_customer_id,
            "address_id": str(address.id),
        }


def test_post_users_creates_user(client: TestClient, seed_data: dict[str, str]) -> None:
    admin_headers = auth_headers(role="wholesale_admin", allowed_addresses=[seed_data["address_id"]])
    response = client.post(
        "/api/v1/users",
        json={
            "email": "bff@example.com",
            "name": "Mario Rossi",
            "role": "reseller",
            "customers": [
                {
                    "customer_id": seed_data["customer_id"],
                    "all_addresses": False,
                    "address_ids": [seed_data["address_id"]],
                }
            ],
            "send_invite": False,
        },
        headers=admin_headers,
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "bff@example.com"
    assert payload["status"] == "invited"


def test_get_me_returns_user_context(client: TestClient, seed_data: dict[str, str]) -> None:
    headers = auth_headers(role="wholesale_admin", allowed_addresses=[seed_data["address_id"]])
    body = {
        "email": "me@example.com",
        "name": "Self",
        "role": "agent",
        "customers": [
            {
                "customer_id": seed_data["customer_erp"],
                "all_addresses": True,
            }
        ],
        "send_invite": False,
    }
    create_resp = client.post("/api/v1/users", json=body, headers=headers)
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    SessionLocal = client.app.state.test_session_local
    kc_id = "kc-user-123"
    with SessionLocal() as session:
        user = session.get(User, UUID(user_id))
        user.kc_user_id = kc_id
        session.commit()

    me_headers = auth_headers(
        role="agent",
        sub=kc_id,
        allowed_addresses=[seed_data["address_id"]],
        allowed_customers=[seed_data["customer_id"]],
    )
    me_resp = client.get(
        "/api/v1/users/me",
        headers=me_headers,
    )
    assert me_resp.status_code == 200
    payload = me_resp.json()
    assert payload["role"] == "agent"
    assert payload["addresses"]
    assert payload["customers"][0]["id"] == seed_data["customer_id"]


def auth_headers(
    *,
    role: str,
    sub: str | None = None,
    allowed_addresses: Iterable[str] | None = None,
    allowed_customers: Iterable[str] | None = None,
) -> dict[str, str]:
    payload = {
        "sub": sub or f"sub-{uuid4()}",
        "role": role,
        "allowed_addresses": list(allowed_addresses or []),
        "allowed_customers": list(allowed_customers or []),
        "email": "tester@example.com",
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
