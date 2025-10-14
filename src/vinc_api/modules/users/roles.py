from __future__ import annotations

from typing import Optional

from .errors import UserServiceError

_ROLE_ALIASES: dict[str, str] = {
    "wholesaler_admin": "supplier_admin",
    "supplier_helpdesk": "wholesaler_helpdesk",
    "agent_admin": "agent",
}

_ALLOWED_ROLES = {
    "reseller",
    "agent",
    "viewer",
    "wholesale_admin",
    "supplier_admin",
    "wholesaler_helpdesk",
    "super_admin",
}


def get_all_application_roles() -> set[str]:
    """
    Returns all application roles including both canonical roles and their aliases.
    Used for filtering roles from JWT tokens.
    """
    return _ALLOWED_ROLES | set(_ROLE_ALIASES.keys())


def canonicalize_role(role: Optional[str]) -> Optional[str]:
    if role is None:
        return None
    canonical = _ROLE_ALIASES.get(role.lower(), role.lower())
    if canonical not in _ALLOWED_ROLES:
        raise UserServiceError(f"Unsupported role '{role}'")
    return canonical
