from __future__ import annotations

from contextlib import contextmanager
import importlib

import pytest
from fastapi.testclient import TestClient

from vinc_api.app import create_app
@pytest.fixture
def client(monkeypatch):
    app = create_app()
    client = TestClient(app)

    public_module = importlib.import_module("vinc_api.modules.public_registration.router")

    fake_admin = object()
    recorded = {
        "ensure_pending_reseller": None,
        "set_user_attributes": None,
        "send_invite": None,
    }

    def fake_get_keycloak_admin():
        return fake_admin

    def fake_create_keycloak_user(
        admin,
        *,
        email: str,
        name: str | None = None,
        temp_password: str | None = None,
        enabled: bool = True,
    ) -> str:
        assert admin is fake_admin
        assert enabled is False or enabled is True
        return "kc-test-id"

    def fake_update_user_profile(admin, user_id, *, email=None, first_name=None, last_name=None):
        assert admin is fake_admin
        assert user_id == "kc-test-id"

    def fake_ensure_realm_role(admin, user_id, role_name):
        assert admin is fake_admin
        assert user_id == "kc-test-id"
        assert role_name == "reseller"

    def fake_set_user_attributes(admin, user_id, *, attributes):
        assert admin is fake_admin
        assert user_id == "kc-test-id"
        recorded["set_user_attributes"] = attributes

    def fake_send_invite(admin, user_id, actions=None, *, settings=None):
        assert admin is fake_admin
        assert user_id == "kc-test-id"
        recorded["send_invite"] = True

    def fake_ensure_pending_reseller(session, *, email, name, keycloak_user_id):
        recorded["ensure_pending_reseller"] = (email, name, keycloak_user_id)

    @contextmanager
    def fake_session():
        yield object()

    class FakeCollection:
        def __init__(self):
            self.documents = []

        async def insert_one(self, doc):
            self.documents.append(doc)

            class Result:
                inserted_id = "mongo-doc-id"

            return Result()

    class FakeMongo:
        def __init__(self):
            self.collection = FakeCollection()

        def __getitem__(self, name):
            assert name == "reseller_registrations"
            return self.collection

    fake_mongo = FakeMongo()

    monkeypatch.setattr(public_module, "get_keycloak_admin", fake_get_keycloak_admin)
    monkeypatch.setattr(public_module, "create_keycloak_user", fake_create_keycloak_user)
    monkeypatch.setattr(public_module, "update_user_profile", fake_update_user_profile)
    monkeypatch.setattr(public_module, "ensure_realm_role", fake_ensure_realm_role)
    monkeypatch.setattr(public_module, "set_user_attributes", fake_set_user_attributes)
    monkeypatch.setattr(public_module, "send_invite", fake_send_invite)
    monkeypatch.setattr(public_module, "ensure_pending_reseller", fake_ensure_pending_reseller)
    monkeypatch.setattr(public_module, "get_session", fake_session)
    monkeypatch.setattr(public_module, "get_mongo_db", lambda: fake_mongo)

    return client, recorded, fake_mongo.collection


def test_retailer_self_registration_success(client):
    client, recorded, collection = client

    payload = {
        "company_name": "Acme Retail",
        "email": "new@retailer.example.com",
        "phone": "+39123456",
        "invite_code": "INV-123",
        "wholesale_slug": "mega-wholesale",
        "locale": "en",
    }

    response = client.post("/api/v1/public/retailer/register", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["keycloak_user_id"] == "kc-test-id"
    assert data["status"] == "pending_review"
    assert data["id"] == "mongo-doc-id"
    assert recorded["ensure_pending_reseller"] == (
        payload["email"].lower(),
        payload["company_name"],
        "kc-test-id",
    )
    assert recorded["set_user_attributes"]["registration_company"] == [payload["company_name"]]
    assert recorded["send_invite"] is True
    assert collection.documents  # registration stored
    stored = collection.documents[0]
    assert stored["email"] == payload["email"].lower()
    assert stored["status"] == "pending_review"


def test_retailer_self_registration_fails_without_admin(monkeypatch):
    app = create_app()
    client = TestClient(app)

    public_module = importlib.import_module("vinc_api.modules.public_registration.router")

    monkeypatch.setattr(public_module, "get_keycloak_admin", lambda: None)

    response = client.post(
        "/api/v1/public/retailer/register",
        json={"company_name": "Missing Admin", "email": "fail@example.com"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Keycloak admin client unavailable"
