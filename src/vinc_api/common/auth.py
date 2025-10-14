from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx
import jwt
from jwt import algorithms, exceptions as jwt_exceptions

from ..core.config import Settings
from ..modules.users.roles import get_all_application_roles


@dataclass(slots=True)
class AuthenticatedUser:
    sub: str
    email: Optional[str]
    role: Optional[str]
    allowed_customer_ids: list[str]
    allowed_address_ids: list[str]
    allowed_wholesaler_ids: list[str]
    multi_tenant: bool
    raw_claims: dict[str, Any]


class JWKSClient:
    def __init__(self, url: str, *, verify_ssl: bool = True, ttl: int = 300, timeout: float = 5.0) -> None:
        self.url = url
        self.verify_ssl = verify_ssl
        self.ttl = ttl
        self.timeout = timeout
        self._jwks: dict[str, Any] | None = None
        self._fetched_at: float = 0.0

    def _refresh(self) -> None:
        try:
            response = httpx.get(self.url, timeout=self.timeout, verify=self.verify_ssl)
            response.raise_for_status()
        except httpx.HTTPError as exc:  # pragma: no cover - network failure path
            raise ValueError(f"Unable to fetch JWKS: {exc}") from exc
        self._jwks = response.json()
        self._fetched_at = time.monotonic()

    def _ensure_keys(self) -> dict[str, Any]:
        if self._jwks is None or (time.monotonic() - self._fetched_at) > self.ttl:
            self._refresh()
        assert self._jwks is not None  # for type-checkers
        return self._jwks

    def get_signing_key(self, kid: str) -> Any:
        jwks = self._ensure_keys()
        keys = jwks.get("keys", [])
        for key in keys:
            if key.get("kid") == kid:
                return algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
        raise ValueError(f"Signing key '{kid}' not found in JWKS")


class JWTVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.JWT_ENABLED
        self.audience = settings.JWT_AUDIENCE
        self.test_secret = settings.JWT_TEST_SECRET
        self.jwks_client: JWKSClient | None = None
        if settings.KEYCLOAK_JWKS_URL:
            self.jwks_client = JWKSClient(
                settings.KEYCLOAK_JWKS_URL,
                verify_ssl=settings.KEYCLOAK_VERIFY_SSL,
                ttl=settings.JWT_CACHE_TTL,
            )

    def decode(self, token: str) -> dict[str, Any]:
        if not self.enabled:
            raise ValueError("JWT verification is disabled")

        if not token:
            raise ValueError("Missing bearer token")

        unverified_header = jwt.get_unverified_header(token)
        algorithm = unverified_header.get("alg")
        if not algorithm:
            raise ValueError("Token missing signing algorithm")

        options = {"verify_aud": bool(self.audience)}

        if algorithm.startswith("HS"):
            if not self.test_secret:
                raise ValueError("HS tokens are not allowed without JWT_TEST_SECRET configured")
            key = self.test_secret
        else:
            kid = unverified_header.get("kid")
            if not kid:
                raise ValueError("Token missing key id (kid)")
            if self.jwks_client is None:
                raise ValueError("JWKS client is not configured")
            key = self.jwks_client.get_signing_key(kid)

        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=[algorithm],
                audience=self.audience,
                options=options,
            )
        except (jwt_exceptions.InvalidTokenError, KeyError) as exc:  # pragma: no cover - passthrough
            raise ValueError(f"Invalid JWT: {exc}") from exc

        return claims

    def authenticate(self, token: str) -> AuthenticatedUser:
        claims = self.decode(token)
        sub = claims.get("sub")
        if not sub:
            raise ValueError("Token missing subject")
        email = claims.get("email") or claims.get("preferred_username")

        # Extract role, filtering out Keycloak system roles
        role = claims.get("role")
        if not role:
            # Get all valid application roles (includes aliases)
            app_roles = get_all_application_roles()
            roles = claims.get("realm_access", {}).get("roles", [])
            for r in roles:
                if r and r.lower() in app_roles:
                    role = r
                    break

        # Parse allowed ids from either space separated strings or list
        customers_claim = claims.get("allowed_customers") or claims.get("allowed_customer_ids")
        addresses_claim = claims.get("allowed_addresses") or claims.get("allowed_address_ids")
        allowed_customers = _ensure_list_of_str(customers_claim)
        allowed_addresses = _ensure_list_of_str(addresses_claim)
        wholesalers_claim = claims.get("allowed_wholesalers")
        allowed_wholesalers = _ensure_list_of_str(wholesalers_claim)
        multi_tenant = _as_bool(claims.get("multi_tenant"))
        return AuthenticatedUser(
            sub=sub,
            email=email,
            role=role,
            allowed_customer_ids=allowed_customers,
            allowed_address_ids=allowed_addresses,
            allowed_wholesaler_ids=allowed_wholesalers,
            multi_tenant=multi_tenant,
            raw_claims=claims,
        )


def _ensure_list_of_str(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if item is None:
                continue
            result.append(str(item))
        return result
    return []


def _as_bool(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return False
