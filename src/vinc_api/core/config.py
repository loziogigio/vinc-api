from __future__ import annotations

from typing import Any


# Try to support both pydantic v2 + pydantic-settings and v1 fallback
try:  # pydantic v2
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore
    V2 = True
except Exception:  # pydantic v1 fallback
    V2 = False
    try:
        from pydantic import BaseSettings, Field  # type: ignore
    except Exception:  # very minimal fallback if pydantic unavailable at import time
        class BaseSettings:  # type: ignore
            def __init__(self, **kwargs: Any) -> None:  # pragma: no cover
                for k, v in kwargs.items():
                    setattr(self, k, v)

        def Field(default=None, **_: Any):  # type: ignore  # pragma: no cover
            return default

    class SettingsConfigDict(dict):  # type: ignore
        pass


class Settings(BaseSettings):
    PROJECT_NAME: str = Field(default="vinc-api")
    ENV: str = Field(default="dev")
    DEBUG: bool = Field(default=True)

    API_V1_PREFIX: str = Field(default="/api/v1")
    CORS_ORIGINS: list[str] | str = Field(default_factory=lambda: ["*"])  # allow list or comma string
    LOG_LEVEL: str = Field(default="INFO")
    TENANT_HEADER: str = Field(default="X-Tenant-ID")

    DATABASE_URL: str | None = Field(default=None)
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)
    DB_POOL_TIMEOUT: float = Field(default=30.0)
    DB_ECHO: bool = Field(default=False)

    REDIS_URL: str | None = Field(default=None)
    REDIS_MAX_CONNECTIONS: int = Field(default=100)
    REDIS_SOCKET_TIMEOUT: float | None = Field(default=None)

    MONGO_URL: str | None = Field(default=None)
    MONGO_DB: str = Field(default="app")
    MONGO_MIN_POOL_SIZE: int = Field(default=0)
    MONGO_MAX_POOL_SIZE: int = Field(default=100)

    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = Field(default=None)
    OTEL_EXPORTER_OTLP_PROTOCOL: str = Field(default="grpc")
    OTEL_EXPORTER_OTLP_HEADERS: str | None = Field(default=None)
    OTEL_SERVICE_NAME: str | None = Field(default=None)
    OTEL_SAMPLE_RATIO: float | None = Field(default=None)
    OTEL_ENABLED: bool = Field(default=True)

    KEYCLOAK_SERVER_URL: str | None = Field(default=None)
    KEYCLOAK_REALM: str | None = Field(default=None)
    KEYCLOAK_ADMIN_CLIENT_ID: str | None = Field(default="admin-cli")
    KEYCLOAK_ADMIN_CLIENT_SECRET: str | None = Field(default=None)
    KEYCLOAK_ADMIN_USERNAME: str | None = Field(default=None)
    KEYCLOAK_ADMIN_PASSWORD: str | None = Field(default=None)
    KEYCLOAK_ADMIN_USER_REALM: str | None = Field(default=None)
    KEYCLOAK_VERIFY_SSL: bool = Field(default=True)
    KEYCLOAK_DEFAULT_INVITE_ACTIONS: list[str] | str = Field(
        default_factory=lambda: ["UPDATE_PASSWORD", "VERIFY_EMAIL"]
    )
    KEYCLOAK_SUPPLIER_ATTRIBUTE: str = Field(default="supplier")
    KEYCLOAK_ALLOWED_CUSTOMERS_ATTRIBUTE: str = Field(default="allowed_customers")
    KEYCLOAK_ALLOWED_ADDRESSES_ATTRIBUTE: str = Field(default="allowed_addresses")
    KEYCLOAK_ALLOWED_WHOLESALERS_ATTRIBUTE: str = Field(default="allowed_wholesalers")
    KEYCLOAK_MULTI_TENANT_ATTRIBUTE: str = Field(default="multi_tenant")
    KEYCLOAK_ROLE_ATTRIBUTE: str = Field(default="role")
    KEYCLOAK_JWKS_URL: str | None = Field(default=None)

    JWT_ENABLED: bool = Field(default=True)
    JWT_AUDIENCE: str | None = Field(default=None)
    JWT_TEST_SECRET: str | None = Field(default=None)
    JWT_CACHE_TTL: int = Field(default=300)
    JWT_ME_CACHE_SECONDS: int = Field(default=30)

    # Debug logging settings
    DEBUG_LOG_HEADERS: bool = Field(default=True)
    DEBUG_LOG_BODY: bool = Field(default=True)
    DEBUG_MAX_BODY_LENGTH: int = Field(default=10000)
    DEBUG_SENSITIVE_HEADERS: list[str] | str = Field(
        default_factory=lambda: ["Authorization", "Cookie", "X-API-Key", "X-Auth-Token"]
    )

    if V2:
        model_config = SettingsConfigDict(  # type: ignore[attr-defined]
            env_file=".env",
            env_prefix="VINC_",
            case_sensitive=False,
            extra="ignore",
        )
    else:  # pydantic v1
        class Config:  # type: ignore[no-redef]
            env_file = ".env"
            case_sensitive = False
            env_prefix = "VINC_"
            extra = "ignore"

    @property
    def cors_origins_list(self) -> list[str]:
        value = self.CORS_ORIGINS
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            if value.strip() == "*":
                return ["*"]
            # split on commas and strip
            return [p.strip() for p in value.split(",") if p.strip()]
        return ["*"]

    @property
    def otel_headers_dict(self) -> dict[str, str]:
        value = self.OTEL_EXPORTER_OTLP_HEADERS
        if not value:
            return {}
        headers: dict[str, str] = {}
        parts = value.split(",")
        for part in parts:
            if "=" not in part:
                continue
            key, val = part.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key:
                headers[key] = val
        return headers

    @property
    def keycloak_invite_actions_list(self) -> list[str]:
        value = self.KEYCLOAK_DEFAULT_INVITE_ACTIONS
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [action.strip() for action in value.split(",") if action.strip()]
        return []

    @property
    def debug_sensitive_headers_list(self) -> list[str]:
        value = self.DEBUG_SENSITIVE_HEADERS
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [header.strip() for header in value.split(",") if header.strip()]
        return ["Authorization", "Cookie", "X-API-Key", "X-Auth-Token"]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
        # normalize CORS to list for starlette
        _settings.CORS_ORIGINS = _settings.cors_origins_list
        _settings.KEYCLOAK_DEFAULT_INVITE_ACTIONS = _settings.keycloak_invite_actions_list
        if (
            not _settings.KEYCLOAK_JWKS_URL
            and _settings.KEYCLOAK_SERVER_URL
            and _settings.KEYCLOAK_REALM
        ):
            base = _settings.KEYCLOAK_SERVER_URL.rstrip("/")
            _settings.KEYCLOAK_JWKS_URL = (
                f"{base}/realms/{_settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
            )
    return _settings
