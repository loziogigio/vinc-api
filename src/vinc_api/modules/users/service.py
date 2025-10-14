from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.config import Settings
from ...core.keycloak import (
    KeycloakServiceError,
    build_user_attributes,
    create_keycloak_user,
    disable_user,
    enable_user,
    format_actions,
    send_invite,
    set_user_attributes,
)
from ..permissions.service import (
    MembershipDoc,
    MembershipEntry as PermissionsMembershipEntry,
    MembershipProcessingError,
    derive_roles_from_memberships,
    load_membership_doc,
    persist_membership_doc,
    process_membership_scope,
)
from .async_utils import await_async
from .db_helpers import (
    customers_info_from_user,
    derive_supplier,
    load_addresses_by_ids,
    load_customers_by_ids,
    load_user_with_relations,
    load_user_with_relations_by_kc_id,
    resolve_customer_selections,
    resolved_from_user,
    supplier_info_from_user,
    suppliers_info_from_user,
)
from .errors import UserServiceError
from .models import Customer, Supplier, User, UserAddressLink, UserCustomerLink, UserSupplierLink
from .roles import canonicalize_role
from .schemas import (
    CustomerSelection,
    SupplierSelection,
    UserCreatedResponse,
    UserCreateRequest,
    UserDetailResponse,
    UserMeResponse,
    UserRole,
    UserStatus,
    UserUpdateRequest,
)

try:  # Keycloak optional at scaffold time
    from keycloak import KeycloakAdmin
except Exception:  # pragma: no cover - allow running without dependency installed
    KeycloakAdmin = None  # type: ignore


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MembershipContext:
    membership_doc: Optional[MembershipDoc]
    supplier_for_stamp: Optional[str]
    allowed_wholesalers: List[str]
    multi_tenant: bool
    supplier_links: List[tuple[UUID, str]] = None  # List of (supplier_id, role) tuples
    customer_ids: List[UUID] = None
    address_ids: List[UUID] = None
    allowed_customer_ids: List[str] = None
    allowed_address_ids: List[str] = None

    def __post_init__(self):
        if self.supplier_links is None:
            self.supplier_links = []
        if self.customer_ids is None:
            self.customer_ids = []
        if self.address_ids is None:
            self.address_ids = []
        if self.allowed_customer_ids is None:
            self.allowed_customer_ids = []
        if self.allowed_address_ids is None:
            self.allowed_address_ids = []


def _normalize_membership_entries(entries: Sequence[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, dict):
            raw = entry
        elif hasattr(entry, "model_dump"):
            raw = entry.model_dump()
        elif hasattr(entry, "dict"):
            raw = entry.dict()
        else:
            raw = dict(entry)
        cleaned = {key: value for key, value in raw.items() if value is not None}
        validated = PermissionsMembershipEntry.model_validate(cleaned)
        normalized.append(validated.model_dump())
    return normalized


def create_user(
    db: Session,
    payload: UserCreateRequest,
    *,
    settings: Settings,
    keycloak_admin: Optional[KeycloakAdmin] = None,
) -> User:
    context = _build_context_for_create(db, payload)

    role_value = _resolve_role(payload.role, context.membership_doc)

    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise UserServiceError("A user with this email already exists")

    user = User(
        email=str(payload.email),
        name=payload.name,
        role=role_value,
        status=UserStatus.INVITED.value,
    )

    _assign_links(user, context.customer_ids, context.address_ids, context.supplier_links)

    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise UserServiceError("Failed to persist user") from exc

    kc_user_id: Optional[str] = None
    if keycloak_admin is not None:
        kc_user_id = _provision_keycloak_user(
            keycloak_admin,
            settings=settings,
            email=str(payload.email),
            name=payload.name,
            supplier=context.supplier_for_stamp,
            allowed_customers=context.allowed_customer_ids,
            allowed_addresses=context.allowed_address_ids,
            allowed_wholesalers=context.allowed_wholesalers,
            multi_tenant=context.multi_tenant,
            role=role_value,
            send_invite_flag=payload.send_invite,
        )

    if kc_user_id:
        user.kc_user_id = kc_user_id
        db.flush()

    _persist_membership(user, context.membership_doc, role_value)
    _emit_user_created_event(user)

    return load_user_with_relations(db, user.id)


def ensure_pending_reseller(
    db: Session,
    *,
    email: str,
    name: str | None,
    keycloak_user_id: str,
) -> User:
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if existing:
        updated = False
        if existing.kc_user_id != keycloak_user_id:
            existing.kc_user_id = keycloak_user_id
            updated = True
        if existing.role != UserRole.RESELLER.value:
            existing.role = UserRole.RESELLER.value
            updated = True
        if existing.status == UserStatus.DISABLED.value:
            existing.status = UserStatus.INVITED.value
            updated = True
        if existing.auth_provider != "keycloak":
            existing.auth_provider = "keycloak"
            updated = True
        if updated:
            db.flush()
        return existing

    user = User(
        email=email,
        name=name,
        role=UserRole.RESELLER.value,
        status=UserStatus.INVITED.value,
        auth_provider="keycloak",
        kc_user_id=keycloak_user_id,
    )

    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise UserServiceError("Failed to persist user") from exc

    return user


def update_user(
    db: Session,
    user_id: UUID,
    payload: UserUpdateRequest,
    *,
    settings: Settings,
    keycloak_admin: Optional[KeycloakAdmin] = None,
) -> User:
    user = load_user_with_relations(db, user_id)

    context, membership_doc_to_persist = _build_context_for_update(db, user, payload)
    _assign_links(user, context.customer_ids, context.address_ids, context.supplier_links)

    resolved_role = _resolve_role(
        payload.role,
        membership_doc_to_persist or context.membership_doc,
    )
    user.role = resolved_role

    try:
        db.flush()
    except IntegrityError as exc:
        raise UserServiceError("Failed to persist user changes") from exc

    if user.kc_user_id and keycloak_admin is not None:
        attributes = build_user_attributes(
            supplier=context.supplier_for_stamp,
            allowed_customers=context.allowed_customer_ids if not context.multi_tenant else [],
            allowed_addresses=context.allowed_address_ids if not context.multi_tenant else [],
            allowed_wholesalers=context.allowed_wholesalers,
            multi_tenant=context.multi_tenant,
            role=user.role,
            settings=settings,
        )
        try:
            set_user_attributes(keycloak_admin, user.kc_user_id, attributes=attributes)
            if user.status == UserStatus.DISABLED.value:
                disable_user(keycloak_admin, user.kc_user_id)
            else:
                enable_user(keycloak_admin, user.kc_user_id)
        except KeycloakServiceError as exc:
            raise UserServiceError(str(exc)) from exc

    _persist_membership(user, membership_doc_to_persist, resolved_role)

    return load_user_with_relations(db, user.id)


def get_user(db: Session, user_id: UUID) -> User:
    return load_user_with_relations(db, user_id)


def get_user_by_kc_id(db: Session, kc_user_id: str) -> User:
    return load_user_with_relations_by_kc_id(db, kc_user_id)


def serialize_user_created(user: User) -> UserCreatedResponse:
    return UserCreatedResponse(id=user.id, email=user.email, status=UserStatus(user.status))


def serialize_user_detail(user: User) -> UserDetailResponse:
    customer_infos = customers_info_from_user(user)
    supplier_info = supplier_info_from_user(user)  # Deprecated, kept for backwards compatibility
    suppliers_info = suppliers_info_from_user(user)  # New field: all associated suppliers
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
        status=UserStatus(user.status),
        kc_user_id=user.kc_user_id,
        supplier=supplier_info,
        suppliers=suppliers_info,
        customers=customer_infos,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def serialize_user_me(user: User) -> UserMeResponse:
    customer_infos = customers_info_from_user(user)
    supplier_info = supplier_info_from_user(user)  # Deprecated, kept for backwards compatibility
    suppliers_info = suppliers_info_from_user(user)  # New field: all associated suppliers
    address_infos = [info for customer in customer_infos for info in customer.addresses]
    return UserMeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
        supplier=supplier_info,
        suppliers=suppliers_info,
        customers=customer_infos,
        addresses=address_infos,
    )


# ---------------------------------------------------------------------------
# Internal helpers


def _build_context_for_create(db: Session, payload: UserCreateRequest) -> MembershipContext:
    memberships_payload = payload.memberships
    if memberships_payload and memberships_payload.memberships:
        doc = MembershipDoc(
            user_key=memberships_payload.user_key or "",
            default_role=memberships_payload.default_role,
            memberships=_normalize_membership_entries(memberships_payload.memberships),
        )
        context = _context_from_memberships(db, doc)
        supplier_links = _process_supplier_selections(db, payload.suppliers or [])
        return MembershipContext(
            membership_doc=doc,
            supplier_for_stamp=context.supplier_for_stamp,
            allowed_wholesalers=context.allowed_wholesalers,
            multi_tenant=context.multi_tenant,
            supplier_links=supplier_links,
            customer_ids=context.customer_ids,
            address_ids=context.address_ids,
            allowed_customer_ids=context.allowed_customer_ids,
            allowed_address_ids=context.allowed_address_ids,
        )

    if not payload.customers:
        raise UserServiceError("At least one customer assignment is required")

    context = _context_from_customers(db, payload.customers)
    supplier_links = _process_supplier_selections(db, payload.suppliers or [])
    return MembershipContext(
        membership_doc=None,
        supplier_for_stamp=context.supplier_for_stamp,
        allowed_wholesalers=context.allowed_wholesalers,
        multi_tenant=context.multi_tenant,
        supplier_links=supplier_links,
        customer_ids=context.customer_ids,
        address_ids=context.address_ids,
        allowed_customer_ids=context.allowed_customer_ids,
        allowed_address_ids=context.allowed_address_ids,
    )


def _build_context_for_update(
    db: Session,
    user: User,
    payload: UserUpdateRequest,
) -> tuple[MembershipContext, Optional[MembershipDoc]]:
    memberships_payload = payload.memberships
    has_memberships = bool(memberships_payload and memberships_payload.memberships)

    existing_membership_doc: Optional[MembershipDoc] = None
    if not has_memberships:
        doc_key = user.kc_user_id or str(user.id)
        existing_membership_doc = await_async(load_membership_doc(doc_key))

    if has_memberships:
        doc = MembershipDoc(
            user_key=memberships_payload.user_key or user.kc_user_id or str(user.id),
            default_role=memberships_payload.default_role,
            memberships=_normalize_membership_entries(memberships_payload.memberships),
        )
        context = _context_from_memberships(db, doc)
        return (
            MembershipContext(
                membership_doc=doc,
                supplier_for_stamp=context.supplier_for_stamp,
                allowed_wholesalers=context.allowed_wholesalers,
                multi_tenant=context.multi_tenant,
                customer_ids=context.customer_ids,
                address_ids=context.address_ids,
                allowed_customer_ids=context.allowed_customer_ids,
                allowed_address_ids=context.allowed_address_ids,
            ),
            doc,
        )

    if payload.customers is not None:
        context = _context_from_customers(db, payload.customers or [])
        return (
            MembershipContext(
                membership_doc=None,
                supplier_for_stamp=context.supplier_for_stamp,
                allowed_wholesalers=context.allowed_wholesalers,
                multi_tenant=context.multi_tenant,
                customer_ids=context.customer_ids,
                address_ids=context.address_ids,
                allowed_customer_ids=context.allowed_customer_ids,
                allowed_address_ids=context.allowed_address_ids,
            ),
            None,
        )

    base_context = _context_from_existing_user(user)
    final_context = MembershipContext(
        membership_doc=None,
        supplier_for_stamp=base_context.supplier_for_stamp,
        allowed_wholesalers=base_context.allowed_wholesalers,
        multi_tenant=base_context.multi_tenant,
        customer_ids=base_context.customer_ids,
        address_ids=base_context.address_ids,
        allowed_customer_ids=base_context.allowed_customer_ids,
        allowed_address_ids=base_context.allowed_address_ids,
    )

    if existing_membership_doc and existing_membership_doc.memberships:
        doc_context = _context_from_memberships(db, existing_membership_doc)
        final_context.allowed_customer_ids = doc_context.allowed_customer_ids or final_context.allowed_customer_ids
        final_context.allowed_address_ids = doc_context.allowed_address_ids or final_context.allowed_address_ids
        final_context.allowed_wholesalers = doc_context.allowed_wholesalers or final_context.allowed_wholesalers
        final_context.supplier_for_stamp = doc_context.supplier_for_stamp or final_context.supplier_for_stamp
        final_context.multi_tenant = doc_context.multi_tenant

    return final_context, None


def _context_from_memberships(db: Session, doc: MembershipDoc) -> MembershipContext:
    try:
        scope = process_membership_scope(db, doc)
    except MembershipProcessingError as exc:
        raise UserServiceError(str(exc))

    customer_ids: List[UUID] = []
    address_ids: List[UUID] = []
    allowed_customer_ids = scope.allowed_customer_ids
    allowed_address_ids = scope.allowed_address_ids

    if not scope.multi_tenant:
        supplier_id = scope.supplier_id
        if not supplier_id:
            raise UserServiceError("Membership scope missing supplier identifier")
        supplier_uuid = _parse_uuid(supplier_id, "Invalid supplier identifier in memberships")
        if db.get(Supplier, supplier_uuid) is None:
            raise UserServiceError("Supplier not found for membership scope")

        customer_records = load_customers_by_ids(
            db,
            scope.allowed_customer_ids,
            expected_supplier_id=supplier_uuid,
        )
        address_records = load_addresses_by_ids(
            db,
            scope.allowed_address_ids,
            expected_supplier_id=supplier_uuid,
        )
        customer_ids = [record.id for record in customer_records]
        address_ids = [record.id for record in address_records]
        allowed_customer_ids = [str(cid) for cid in customer_ids]
        allowed_address_ids = [str(aid) for aid in address_ids]

    return MembershipContext(
        membership_doc=doc,
        supplier_for_stamp=scope.supplier_id,
        allowed_wholesalers=scope.allowed_wholesalers,
        multi_tenant=scope.multi_tenant,
        customer_ids=customer_ids,
        address_ids=address_ids,
        allowed_customer_ids=allowed_customer_ids,
        allowed_address_ids=allowed_address_ids,
    )


def _context_from_customers(db: Session, customers: Sequence[CustomerSelection]) -> MembershipContext:
    selections = resolve_customer_selections(db, customers)
    address_ids: List[UUID] = [addr.id for selection in selections for addr in selection.addresses]
    if not address_ids:
        raise UserServiceError("At least one active customer address is required")

    supplier = derive_supplier(selections)
    supplier_id = str(supplier.id)
    customer_ids = [selection.customer.id for selection in selections]

    return MembershipContext(
        membership_doc=None,
        supplier_for_stamp=supplier_id,
        allowed_wholesalers=[supplier_id],
        multi_tenant=False,
        customer_ids=customer_ids,
        address_ids=address_ids,
        allowed_customer_ids=[str(cid) for cid in customer_ids],
        allowed_address_ids=[str(aid) for aid in address_ids],
    )


def _context_from_existing_user(user: User) -> MembershipContext:
    resolved = resolved_from_user(user)
    customer_ids = [selection.customer.id for selection in resolved]
    address_ids = [addr.id for selection in resolved for addr in selection.addresses]

    try:
        supplier = derive_supplier(resolved)
        supplier_id = str(supplier.id)
        allowed_wholesalers = [supplier_id]
    except UserServiceError:
        supplier_id = None
        allowed_wholesalers = []

    return MembershipContext(
        membership_doc=None,
        supplier_for_stamp=supplier_id,
        allowed_wholesalers=allowed_wholesalers,
        multi_tenant=False,
        customer_ids=customer_ids,
        address_ids=address_ids,
        allowed_customer_ids=[str(cid) for cid in customer_ids],
        allowed_address_ids=[str(aid) for aid in address_ids],
    )


def _process_supplier_selections(db: Session, selections: List[SupplierSelection]) -> List[tuple[UUID, str]]:
    """Process supplier selections and return list of (supplier_id, role) tuples."""
    if not selections:
        return []

    result = []
    for selection in selections:
        try:
            supplier_id = UUID(selection.supplier_id)
        except (ValueError, AttributeError):
            raise UserServiceError(f"Invalid supplier ID: {selection.supplier_id}")

        # Validate supplier exists
        supplier = db.execute(select(Supplier).where(Supplier.id == supplier_id)).scalar_one_or_none()
        if not supplier:
            raise UserServiceError(f"Supplier not found: {selection.supplier_id}")

        # Validate role
        valid_roles = {"admin", "helpdesk", "viewer"}
        role = selection.role if selection.role in valid_roles else "viewer"

        result.append((supplier_id, role))

    return result


def _assign_links(
    user: User,
    customer_ids: Sequence[UUID],
    address_ids: Sequence[UUID],
    supplier_links: Sequence[tuple[UUID, str]] = None,
) -> None:
    user.customer_links = [
        UserCustomerLink(customer_id=cid, role="buyer") for cid in customer_ids
    ]
    user.address_links = [
        UserAddressLink(customer_address_id=aid, role="buyer") for aid in address_ids
    ]
    if supplier_links:
        user.supplier_links = [
            UserSupplierLink(supplier_id=sid, role=role) for sid, role in supplier_links
        ]


def _resolve_role(payload_role: Optional[UserRole], membership_doc: Optional[MembershipDoc]) -> str:
    role_value = payload_role.value if payload_role is not None else None
    if role_value is None and membership_doc is not None:
        roles = derive_roles_from_memberships(membership_doc)
        if membership_doc.default_role:
            roles.insert(0, membership_doc.default_role)
        if roles:
            role_value = roles[0]
    role_value = canonicalize_role(role_value)
    if role_value is None:
        raise UserServiceError("Role is required")
    return role_value


def _provision_keycloak_user(
    keycloak_admin: KeycloakAdmin,
    *,
    settings: Settings,
    email: str,
    name: Optional[str],
    supplier: Optional[str],
    allowed_customers: List[str],
    allowed_addresses: List[str],
    allowed_wholesalers: List[str],
    multi_tenant: bool,
    role: str,
    send_invite_flag: bool,
) -> str:
    try:
        kc_user_id = create_keycloak_user(
            keycloak_admin,
            email=email,
            name=name,
            enabled=True,
        )
        attributes = build_user_attributes(
            supplier=supplier,
            allowed_customers=allowed_customers if not multi_tenant else [],
            allowed_addresses=allowed_addresses if not multi_tenant else [],
            allowed_wholesalers=allowed_wholesalers,
            multi_tenant=multi_tenant,
            role=role,
            settings=settings,
        )
        set_user_attributes(keycloak_admin, kc_user_id, attributes=attributes)
        enable_user(keycloak_admin, kc_user_id)
        if send_invite_flag:
            actions = format_actions(None, settings=settings)
            send_invite(keycloak_admin, kc_user_id, actions=actions, settings=settings)
        return kc_user_id
    except KeycloakServiceError as exc:
        raise UserServiceError(str(exc)) from exc


def _persist_membership(user: User, doc: Optional[MembershipDoc], resolved_role: str) -> None:
    if doc is None:
        return
    persist_key = user.kc_user_id or doc.user_key or str(user.id)
    stored_doc = MembershipDoc(
        user_key=persist_key,
        default_role=doc.default_role or resolved_role,
        memberships=doc.memberships,
    )
    try:
        await_async(persist_membership_doc(stored_doc))
    except RuntimeError as exc:
        raise UserServiceError("Membership store unavailable") from exc


def list_users(
    db: Session,
    *,
    supplier_id: Optional[UUID] = None,
    search: Optional[str] = None,
) -> List[User]:
    """
    List users with optional filtering by supplier and search.

    Args:
        supplier_id: Filter users by supplier according to access control rules:
                     - Users created by this supplier (user.supplier_id = supplier_id)
                     - OR users linked to customers owned by this supplier
    """
    from sqlalchemy import or_
    from sqlalchemy.orm import selectinload
    from .models import UserCustomerLink, Customer

    stmt = (
        select(User)
        .options(
            selectinload(User.customer_links).selectinload(UserCustomerLink.customer).selectinload(Customer.supplier)
        )
        .order_by(User.email.asc())
    )

    # Filter by supplier if provided - implements access control specification
    if supplier_id:
        stmt = stmt.where(
            or_(
                User.supplier_id == supplier_id,
                User.id.in_(
                    select(UserCustomerLink.user_id)
                    .join(Customer, UserCustomerLink.customer_id == Customer.id)
                    .where(Customer.supplier_id == supplier_id)
                )
            )
        )

    # Add search filter
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(search_term),
                User.name.ilike(search_term),
                User.role.ilike(search_term),
            )
        )

    users = db.scalars(stmt).unique().all()
    return list(users)


def serialize_users(users: Sequence[User]) -> List[UserDetailResponse]:
    """Serialize a list of users to UserDetailResponse."""
    return [serialize_user_detail(user) for user in users]


def list_users_paginated(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    role_filter: Optional[str] = None,
    status_filter: Optional[str] = None,
    supplier_id: Optional[UUID] = None,
) -> tuple[List[User], int]:
    """
    List users with pagination, search, and filters.

    Args:
        supplier_id: Filter users by supplier according to access control rules:
                     - Users created by this supplier (user.supplier_id = supplier_id)
                     - OR users linked to customers owned by this supplier

    Returns (users, total_count).
    """
    from sqlalchemy import func, or_
    from sqlalchemy.orm import selectinload

    # Base query
    stmt = (
        select(User)
        .options(
            selectinload(User.supplier_links),
            selectinload(User.customer_links),
            selectinload(User.address_links),
        )
        .order_by(User.created_at.desc())
    )

    # Supplier filter - implements access control specification
    if supplier_id:
        # Filter users according to specification:
        # 1. Users created by this supplier (user.supplier_id = supplier_id)
        # 2. Users linked to customers owned by this supplier (via user_customer_link)
        stmt = stmt.where(
            or_(
                User.supplier_id == supplier_id,
                User.id.in_(
                    select(UserCustomerLink.user_id)
                    .join(Customer, UserCustomerLink.customer_id == Customer.id)
                    .where(Customer.supplier_id == supplier_id)
                )
            )
        )

    # Search filter
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(search_term),
                User.name.ilike(search_term),
                User.role.ilike(search_term),
            )
        )

    # Role filter
    if role_filter:
        stmt = stmt.where(User.role == role_filter)

    # Status filter
    if status_filter:
        stmt = stmt.where(User.status == status_filter)

    # Get total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    # Apply pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)

    # Execute query
    users = db.scalars(stmt).unique().all()

    return list(users), total


def serialize_user_list_item(user: User) -> dict:
    """Serialize a user to UserListItemResponse with link counts."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "status": user.status,
        "supplier_count": len(user.supplier_links) if user.supplier_links else 0,
        "customer_count": len(user.customer_links) if user.customer_links else 0,
        "address_count": len(user.address_links) if user.address_links else 0,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _parse_uuid(value: str, error_message: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise UserServiceError(error_message) from exc


def _emit_user_created_event(user: User) -> None:
    logger.info(
        "UserCreated event",
        extra={
            "user_id": str(user.id),
            "email": user.email,
            "role": user.role,
            "status": user.status,
        },
    )


# ---------------------------------------------------------------------------
# Customer association management
# ---------------------------------------------------------------------------


def add_user_customer_association(
    db: Session,
    user_id: UUID,
    payload: dict,
) -> User:
    """Add a customer association to a user."""
    user = get_user(db, user_id)

    customer_id = payload.get("customer_id")
    if not customer_id:
        raise UserServiceError("customer_id is required")

    try:
        customer_uuid = UUID(customer_id)
    except ValueError:
        raise UserServiceError("Invalid customer_id format")

    all_addresses = payload.get("all_addresses", False)
    address_ids = payload.get("address_ids", [])
    role = payload.get("role", "buyer")

    # Check if customer already exists for this user
    existing_link = db.scalar(
        select(UserCustomerLink).where(
            UserCustomerLink.user_id == user_id,
            UserCustomerLink.customer_id == customer_uuid
        )
    )
    if existing_link:
        raise UserServiceError("Customer association already exists", status_code="409")

    # Load customer and its addresses
    from .models import Customer, CustomerAddress
    customer = db.get(Customer, customer_uuid)
    if not customer:
        raise UserServiceError("Customer not found", status_code="404")

    # Create customer link
    customer_link = UserCustomerLink(
        user_id=user_id,
        customer_id=customer_uuid,
        role=role
    )
    db.add(customer_link)

    # Add address links
    if all_addresses:
        # Get all addresses for this customer
        addresses = db.scalars(
            select(CustomerAddress).where(
                CustomerAddress.erp_customer_id == customer.erp_customer_id
            )
        ).all()
        address_ids = [str(addr.id) for addr in addresses]

    for addr_id in address_ids:
        try:
            addr_uuid = UUID(addr_id)
        except ValueError:
            continue

        # Check if address link already exists
        existing_addr_link = db.scalar(
            select(UserAddressLink).where(
                UserAddressLink.user_id == user_id,
                UserAddressLink.customer_address_id == addr_uuid
            )
        )
        if not existing_addr_link:
            addr_link = UserAddressLink(
                user_id=user_id,
                customer_address_id=addr_uuid,
                role=role
            )
            db.add(addr_link)

    db.commit()
    db.refresh(user)

    return load_user_with_relations(db, user_id)


def update_user_customer_association(
    db: Session,
    user_id: UUID,
    customer_id: UUID,
    payload: dict,
) -> User:
    """Update a customer association for a user."""
    user = get_user(db, user_id)

    # Check if customer link exists
    customer_link = db.scalar(
        select(UserCustomerLink).where(
            UserCustomerLink.user_id == user_id,
            UserCustomerLink.customer_id == customer_id
        )
    )
    if not customer_link:
        raise UserServiceError("Customer association not found", status_code="404")

    all_addresses = payload.get("all_addresses", False)
    address_ids = payload.get("address_ids", [])
    role = payload.get("role", "buyer")

    # Update role if provided
    customer_link.role = role

    # Remove existing address links for this customer
    from .models import Customer, CustomerAddress
    customer = db.get(Customer, customer_id)
    if not customer:
        raise UserServiceError("Customer not found", status_code="404")

    # Delete old address links for this customer
    existing_addresses = db.scalars(
        select(CustomerAddress).where(
            CustomerAddress.erp_customer_id == customer.erp_customer_id
        )
    ).all()

    for addr in existing_addresses:
        db.execute(
            select(UserAddressLink).where(
                UserAddressLink.user_id == user_id,
                UserAddressLink.customer_address_id == addr.id
            )
        )
        db.query(UserAddressLink).filter(
            UserAddressLink.user_id == user_id,
            UserAddressLink.customer_address_id == addr.id
        ).delete()

    # Add new address links
    if all_addresses:
        address_ids = [str(addr.id) for addr in existing_addresses]

    for addr_id in address_ids:
        try:
            addr_uuid = UUID(addr_id)
        except ValueError:
            continue

        addr_link = UserAddressLink(
            user_id=user_id,
            customer_address_id=addr_uuid,
            role=role
        )
        db.add(addr_link)

    db.commit()
    db.refresh(user)

    return load_user_with_relations(db, user_id)


def delete_user_customer_association(
    db: Session,
    user_id: UUID,
    customer_id: UUID,
) -> None:
    """Remove a customer association from a user."""
    user = get_user(db, user_id)

    # Check if customer link exists
    customer_link = db.scalar(
        select(UserCustomerLink).where(
            UserCustomerLink.user_id == user_id,
            UserCustomerLink.customer_id == customer_id
        )
    )
    if not customer_link:
        raise UserServiceError("Customer association not found", status_code="404")

    # Get customer to find all related addresses
    from .models import Customer, CustomerAddress
    customer = db.get(Customer, customer_id)
    if customer:
        # Delete all address links for this customer
        addresses = db.scalars(
            select(CustomerAddress).where(
                CustomerAddress.erp_customer_id == customer.erp_customer_id
            )
        ).all()

        for addr in addresses:
            db.query(UserAddressLink).filter(
                UserAddressLink.user_id == user_id,
                UserAddressLink.customer_address_id == addr.id
            ).delete()

    # Delete customer link
    db.delete(customer_link)
    db.commit()
