from __future__ import annotations

import argparse
import sys
from typing import Optional

from sqlalchemy import select

from ..core.config import get_settings
from ..core.db import get_session, init_engine
from ..core.keycloak import (
    KeycloakServiceError,
    build_user_attributes,
    create_keycloak_user,
    enable_user,
    get_keycloak_admin,
    init_keycloak,
    set_user_attributes,
)
from ..modules.users.models import User

try:  # pragma: no cover - optional when keycloak absent
    from keycloak.exceptions import (
        KeycloakAuthenticationError,
        KeycloakConnectionError,
        KeycloakGetError,
        KeycloakPostError,
        KeycloakPutError,
    )
except Exception:  # pragma: no cover - align with optional dependency
    KeycloakAuthenticationError = Exception  # type: ignore
    KeycloakConnectionError = Exception  # type: ignore
    KeycloakGetError = Exception  # type: ignore
    KeycloakPostError = Exception  # type: ignore
    KeycloakPutError = Exception  # type: ignore


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or update a Keycloak-backed super admin user",
    )
    parser.add_argument("--email", required=True, help="Email for the super admin user")
    parser.add_argument("--name", default=None, help="Display name for the user")
    parser.add_argument(
        "--temp-password",
        dest="temp_password",
        default=None,
        help="Temporary password to set in Keycloak (forces reset on first login)",
    )
    parser.add_argument(
        "--no-activate",
        action="store_true",
        help="Create the record but leave status as invited",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    settings = get_settings()

    init_engine(settings=settings)
    try:
        init_keycloak(settings)
    except (KeycloakAuthenticationError, KeycloakConnectionError) as exc:
        sys.stderr.write("Failed to initialise Keycloak admin client. Check admin credentials and server URL.\n")
        sys.stderr.write(f"Details: {exc}\n")
        return 1

    keycloak_admin = get_keycloak_admin()

    if keycloak_admin is None:
        sys.stderr.write("Keycloak admin client is not configured or failed to initialise.\n")
        return 1

    with get_session() as session:
        if session is None:
            sys.stderr.write("Database session could not be created. Check DATABASE_URL.\n")
            return 1

        stmt = select(User).where(User.email == args.email)
        user = session.execute(stmt).scalar_one_or_none()
        created = False

        if user is None:
            user = User(email=args.email, name=args.name, role="super_admin")
            if args.no_activate:
                user.status = "invited"
            else:
                user.status = "active"
            user.auth_provider = "keycloak"
            session.add(user)
            session.flush()
            created = True
        else:
            if args.name and user.name != args.name:
                user.name = args.name
            user.role = "super_admin"
            user.auth_provider = "keycloak"
            if args.no_activate:
                user.status = "invited"
            else:
                user.status = "active"

        kc_user_id: Optional[str] = user.kc_user_id

        try:
            if kc_user_id:
                try:
                    keycloak_admin.get_user(kc_user_id)
                except KeycloakGetError:
                    kc_user_id = None
            if not kc_user_id:
                try:
                    kc_user_id = keycloak_admin.get_user_id(args.email)
                except KeycloakGetError:
                    kc_user_id = None
            if not kc_user_id:
                kc_user_id = create_keycloak_user(
                    keycloak_admin,
                    email=args.email,
                    name=args.name,
                    temp_password=args.temp_password,
                    enabled=not args.no_activate,
                )
            elif args.temp_password:
                keycloak_admin.set_user_password(
                    kc_user_id,
                    args.temp_password,
                    temporary=True,
                )

            attributes = build_user_attributes(role="super_admin", settings=settings)
            set_user_attributes(keycloak_admin, kc_user_id, attributes=attributes)
            enable_user(keycloak_admin, kc_user_id)

            # Synchronise realm role assignment so it appears in the Keycloak UI
            try:
                current_roles = keycloak_admin.get_realm_roles_of_user(kc_user_id)
                current_names = {role.get("name") for role in current_roles}
                if "super_admin" not in current_names:
                    realm_role = keycloak_admin.get_realm_role("super_admin")
                    keycloak_admin.assign_realm_roles(kc_user_id, [realm_role])
            except (KeycloakGetError, KeycloakPostError) as exc:
                sys.stderr.write(
                    f"Failed to assign Keycloak realm role 'super_admin': {exc}\n"
                )
                session.rollback()
                return 1

            user.kc_user_id = kc_user_id
            session.flush()

        except (
            KeycloakServiceError,
            KeycloakGetError,
            KeycloakPutError,
            KeycloakPostError,
            KeycloakAuthenticationError,
            KeycloakConnectionError,
        ) as exc:
            if isinstance(exc, KeycloakAuthenticationError):
                sys.stderr.write(
                    "Keycloak authentication failed while provisioning user. "
                    "Verify admin credentials.\n"
                )
            else:
                sys.stderr.write(
                    f"Keycloak error while provisioning user: {exc}\n"
                )
            session.rollback()
            return 1

    status = "created" if created else "updated"
    sys.stdout.write(
        f"Super admin {status} successfully. Email: {args.email}, Keycloak ID: {kc_user_id}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - script entry point
    raise SystemExit(main())
