from fastapi.testclient import TestClient

from vic_api.app import create_app
from vic_api.core.config import Settings


def test_health():
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
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
