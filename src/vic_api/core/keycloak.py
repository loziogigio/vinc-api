from __future__ import annotations

from typing import Any, Iterable, Optional

from .config import Settings, get_settings

try:  # optional dependency at scaffold time
    from keycloak import KeycloakAdmin
    from keycloak.exceptions import (
        KeycloakAuthenticationError,
        KeycloakConnectionError,
        KeycloakGetError,
        KeycloakPostError,
        KeycloakPutError,
    )
except Exception:  # pragma: no cover - allow import without dependency
    KeycloakAdmin = None  # type: ignore
    KeycloakAuthenticationError = Exception  # type: ignore
    KeycloakConnectionError = Exception  # type: ignore
    KeycloakGetError = KeycloakPostError = KeycloakPutError = Exception  # type: ignore


_keycloak_admin: Optional[KeycloakAdmin] = None


class KeycloakServiceError(Exception):
    """Lightweight wrapper for surfacing Keycloak admin errors."""

    pass


def init_keycloak(settings: Settings | None = None) -> None:
    """Initialise and cache a Keycloak admin client when configuration is present."""
    global _keycloak_admin

    if KeycloakAdmin is None:
        _keycloak_admin = None
        return

    settings = settings or get_settings()

    if not settings.KEYCLOAK_SERVER_URL or not settings.KEYCLOAK_REALM:
        _keycloak_admin = None
        return

    if not settings.KEYCLOAK_ADMIN_USERNAME or not settings.KEYCLOAK_ADMIN_PASSWORD:
        _keycloak_admin = None
        return

    server_url = settings.KEYCLOAK_SERVER_URL.rstrip("/") + "/"

    try:
        user_realm = settings.KEYCLOAK_ADMIN_USER_REALM or settings.KEYCLOAK_REALM
        _keycloak_admin = KeycloakAdmin(
            server_url=server_url,
            username=settings.KEYCLOAK_ADMIN_USERNAME,
            password=settings.KEYCLOAK_ADMIN_PASSWORD,
            realm_name=settings.KEYCLOAK_REALM,
            user_realm_name=user_realm,
            client_id=settings.KEYCLOAK_ADMIN_CLIENT_ID,
            client_secret_key=settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
            verify=settings.KEYCLOAK_VERIFY_SSL,
        )
    except (KeycloakAuthenticationError, KeycloakConnectionError):  # pragma: no cover
        _keycloak_admin = None
        raise


def get_keycloak_admin() -> Optional[KeycloakAdmin]:
    """Return the cached Keycloak admin client if available."""
    if _keycloak_admin is None:
        init_keycloak()
    return _keycloak_admin


def is_keycloak_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(
        settings.KEYCLOAK_SERVER_URL
        and settings.KEYCLOAK_REALM
        and settings.KEYCLOAK_ADMIN_USERNAME
        and settings.KEYCLOAK_ADMIN_PASSWORD
    )


def format_actions(actions: Iterable[str] | None, settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    default_actions = list(settings.KEYCLOAK_DEFAULT_INVITE_ACTIONS)
    if not actions:
        return default_actions
    cleaned = [action.strip() for action in actions if action.strip()]
    return cleaned or default_actions


def build_user_attributes(
    *,
    supplier: str | None = None,
    allowed_customers: Iterable[str] | None = None,
    allowed_addresses: Iterable[str] | None = None,
    role: str | None = None,
    settings: Settings | None = None,
) -> dict[str, list[str]]:
    settings = settings or get_settings()
    attributes: dict[str, list[str]] = {}

    if supplier:
        attributes[settings.KEYCLOAK_SUPPLIER_ATTRIBUTE] = [supplier]
    if allowed_customers:
        customers = [value for value in allowed_customers if value]
        if customers:
            attributes[settings.KEYCLOAK_ALLOWED_CUSTOMERS_ATTRIBUTE] = customers
    if allowed_addresses:
        addresses = [value for value in allowed_addresses if value]
        if addresses:
            attributes[settings.KEYCLOAK_ALLOWED_ADDRESSES_ATTRIBUTE] = addresses
    if role:
        attributes[settings.KEYCLOAK_ROLE_ATTRIBUTE] = [role]
    return attributes


def reset_keycloak_admin() -> None:
    """Clear cached Keycloak client (mainly for tests)."""
    global _keycloak_admin
    _keycloak_admin = None


def create_keycloak_user(
    admin: KeycloakAdmin,
    *,
    email: str,
    name: str | None = None,
    temp_password: str | None = None,
    enabled: bool = True,
) -> str:
    payload: dict[str, Any] = {
        "email": email,
        "username": email,
        "firstName": name or "",
        "enabled": enabled,
        "emailVerified": False,
    }
    if temp_password:
        payload["credentials"] = [
            {
                "type": "password",
                "value": temp_password,
                "temporary": True,
            }
        ]

    try:
        result = admin.create_user(payload)
    except (KeycloakAuthenticationError, KeycloakConnectionError, KeycloakPostError) as exc:
        raise KeycloakServiceError(f"Failed to create Keycloak user: {exc}") from exc

    user_id: Optional[str] = None
    if isinstance(result, str) and result:
        user_id = result
    elif isinstance(result, dict) and result.get("id"):
        user_id = result["id"]
    if not user_id:
        try:
            user_id = admin.get_user_id(email)
        except KeycloakGetError as exc:  # pragma: no cover - defensive
            raise KeycloakServiceError("Keycloak user created but ID lookup failed") from exc

    return user_id


def set_user_attributes(admin: KeycloakAdmin, user_id: str, *, attributes: dict[str, Any]) -> None:
    payload = {"attributes": attributes}
    try:
        admin.update_user(user_id=user_id, payload=payload)
    except (KeycloakAuthenticationError, KeycloakConnectionError, KeycloakPutError, KeycloakGetError) as exc:
        raise KeycloakServiceError(f"Failed to update Keycloak user attributes: {exc}") from exc


def enable_user(admin: KeycloakAdmin, user_id: str) -> None:
    _toggle_user_enabled(admin, user_id, True)


def disable_user(admin: KeycloakAdmin, user_id: str) -> None:
    _toggle_user_enabled(admin, user_id, False)


def send_invite(admin: KeycloakAdmin, user_id: str, actions: Iterable[str] | None = None) -> None:
    try:
        admin.execute_actions_email(user_id=user_id, actions=list(actions or ["UPDATE_PASSWORD"]))
    except (KeycloakAuthenticationError, KeycloakConnectionError, KeycloakGetError) as exc:
        raise KeycloakServiceError(f"Failed to trigger Keycloak invite: {exc}") from exc


def _toggle_user_enabled(admin: KeycloakAdmin, user_id: str, enabled: bool) -> None:
    try:
        admin.update_user(user_id=user_id, payload={"enabled": enabled})
    except (KeycloakAuthenticationError, KeycloakConnectionError, KeycloakPutError, KeycloakGetError) as exc:
        verb = "enable" if enabled else "disable"
        raise KeycloakServiceError(f"Failed to {verb} Keycloak user: {exc}") from exc
