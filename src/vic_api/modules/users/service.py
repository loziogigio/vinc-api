from __future__ import annotations

import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import Iterable, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

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
from .models import (
    Customer,
    CustomerAddress,
    Supplier,
    User,
    UserAddressLink,
    UserCustomerLink,
)
from .schemas import (
    AddressInfo,
    CustomerInfo,
    CustomerSelection,
    SupplierInfo,
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
class UserServiceError(Exception):
    detail: str
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST

    def __str__(self) -> str:  # pragma: no cover
        return self.detail


@dataclass(slots=True)
class ResolvedCustomerSelection:
    customer: Customer
    addresses: List[CustomerAddress]


def create_user(
    db: Session,
    payload: UserCreateRequest,
    *,
    settings: Settings,
    keycloak_admin: Optional[KeycloakAdmin] = None,
) -> User:
    if not payload.customers:
        raise UserServiceError("At least one customer assignment is required")

    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise UserServiceError("A user with this email already exists", HTTPStatus.CONFLICT)

    resolved = _resolve_customer_selections(db, payload.customers)
    all_addresses = [addr for r in resolved for addr in r.addresses]
    if not all_addresses:
        raise UserServiceError("At least one active customer address is required")

    supplier = _derive_supplier(resolved)

    user = User(
        email=str(payload.email),
        name=payload.name,
        role=payload.role.value,
        status=UserStatus.INVITED.value,
    )

    user.customer_links = [
        UserCustomerLink(customer_id=res.customer.id, role="buyer") for res in resolved
    ]
    user.address_links = [
        UserAddressLink(customer_address_id=addr.id, role="buyer")
        for addr in all_addresses
    ]

    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        raise UserServiceError("Failed to persist user", HTTPStatus.BAD_REQUEST) from exc

    kc_user_id: Optional[str] = None
    if keycloak_admin is not None:
        try:
            kc_user_id = create_keycloak_user(
                keycloak_admin,
                email=str(payload.email),
                name=payload.name,
                enabled=True,
            )
            attributes = build_user_attributes(
                supplier=str(supplier.id),
                allowed_customers=[str(res.customer.id) for res in resolved],
                allowed_addresses=[str(addr.id) for addr in all_addresses],
                role=payload.role.value,
                settings=settings,
            )
            set_user_attributes(keycloak_admin, kc_user_id, attributes=attributes)
            enable_user(keycloak_admin, kc_user_id)
            if payload.send_invite:
                actions = format_actions(None, settings=settings)
                send_invite(keycloak_admin, kc_user_id, actions=actions)
        except KeycloakServiceError as exc:
            raise UserServiceError(str(exc), HTTPStatus.BAD_GATEWAY) from exc

    if kc_user_id:
        user.kc_user_id = kc_user_id
        db.flush()

    _emit_user_created_event(user)

    return _load_user_with_relations(db, user.id)


def update_user(
    db: Session,
    user_id: UUID,
    payload: UserUpdateRequest,
    *,
    settings: Settings,
    keycloak_admin: Optional[KeycloakAdmin] = None,
) -> User:
    user = _load_user_with_relations(db, user_id)

    if payload.role is not None:
        user.role = payload.role.value

    resolved: Optional[List[ResolvedCustomerSelection]] = None
    if payload.customers is not None:
        if not payload.customers:
            raise UserServiceError("At least one customer assignment is required")
        resolved = _resolve_customer_selections(db, payload.customers)
        all_addresses = [addr for r in resolved for addr in r.addresses]
        if not all_addresses:
            raise UserServiceError("At least one active customer address is required")

        user.customer_links = [
            UserCustomerLink(customer_id=res.customer.id, role="buyer")
            for res in resolved
        ]
        user.address_links = [
            UserAddressLink(customer_address_id=addr.id, role="buyer")
            for addr in all_addresses
        ]

    try:
        db.flush()
    except IntegrityError as exc:
        raise UserServiceError("Failed to persist user changes", HTTPStatus.BAD_REQUEST) from exc

    if user.kc_user_id and keycloak_admin is not None:
        if resolved is None:
            # reload relationships to ensure we have latest state for attribute sync
            user = _load_user_with_relations(db, user_id)
            resolved = _resolved_from_user(user)
        supplier = _derive_supplier(resolved)
        addresses = [addr for res in resolved for addr in res.addresses]
        attributes = build_user_attributes(
            supplier=str(supplier.id),
            allowed_customers=[str(res.customer.id) for res in resolved],
            allowed_addresses=[str(addr.id) for addr in addresses],
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
            raise UserServiceError(str(exc), HTTPStatus.BAD_GATEWAY) from exc

    return _load_user_with_relations(db, user.id)


def get_user(db: Session, user_id: UUID) -> User:
    return _load_user_with_relations(db, user_id)


def get_user_by_kc_id(db: Session, kc_user_id: str) -> User:
    stmt: Select[tuple[User]] = (
        select(User)
        .options(
            selectinload(User.address_links)
            .selectinload(UserAddressLink.customer_address)
            .selectinload(CustomerAddress.supplier),
            selectinload(User.customer_links).selectinload(UserCustomerLink.customer),
        )
        .where(User.kc_user_id == kc_user_id)
    )
    user = db.execute(stmt).scalars().unique().one_or_none()
    if user is None:
        raise UserServiceError("User not found", HTTPStatus.NOT_FOUND)
    return user


def serialize_user_created(user: User) -> UserCreatedResponse:
    return UserCreatedResponse(id=user.id, email=user.email, status=UserStatus(user.status))


def serialize_user_detail(user: User) -> UserDetailResponse:
    supplier_info = _supplier_info_from_user(user)
    customer_infos = _customers_info_from_user(user)
    return UserDetailResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
        status=UserStatus(user.status),
        kc_user_id=user.kc_user_id,
        supplier=supplier_info,
        customers=customer_infos,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def serialize_user_me(user: User) -> UserMeResponse:
    supplier_info = _supplier_info_from_user(user)
    customer_infos = _customers_info_from_user(user)
    address_infos = [info for customer in customer_infos for info in customer.addresses]
    return UserMeResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        role=UserRole(user.role),
        supplier=supplier_info,
        customers=customer_infos,
        addresses=address_infos,
    )


# Helpers ------------------------------------------------------------------

def _load_user_with_relations(db: Session, user_id: UUID) -> User:
    stmt: Select[tuple[User]] = (
        select(User)
        .options(
            selectinload(User.address_links)
            .selectinload(UserAddressLink.customer_address)
            .selectinload(CustomerAddress.supplier),
            selectinload(User.customer_links).selectinload(UserCustomerLink.customer),
        )
        .where(User.id == user_id)
    )
    user = db.execute(stmt).scalars().unique().one_or_none()
    if user is None:
        raise UserServiceError("User not found", HTTPStatus.NOT_FOUND)
    return user


def _resolve_customer_selections(
    db: Session, selections: Sequence[CustomerSelection]
) -> List[ResolvedCustomerSelection]:
    resolved: List[ResolvedCustomerSelection] = []
    seen_customers: set[UUID] = set()
    seen_addresses: set[UUID] = set()

    for selection in selections:
        customer = _get_customer_by_identifier(db, selection.customer_id)
        if customer.id in seen_customers:
            raise UserServiceError("Duplicate customer assignment is not allowed")

        addresses = _resolve_addresses_for_customer(
            db,
            customer,
            selection.all_addresses,
            selection.address_ids or [],
        )
        if not addresses:
            raise UserServiceError(
                f"Customer '{customer.erp_customer_id}' does not have active addresses for selection"
            )

        duplicate_addresses = seen_addresses.intersection({addr.id for addr in addresses})
        if duplicate_addresses:
            raise UserServiceError("Duplicate customer address assignments are not allowed")

        seen_customers.add(customer.id)
        seen_addresses.update(addr.id for addr in addresses)
        resolved.append(ResolvedCustomerSelection(customer=customer, addresses=addresses))

    return resolved


def _get_customer_by_identifier(db: Session, identifier: str) -> Customer:
    customer: Optional[Customer] = None
    try:
        customer_id = UUID(identifier)
    except ValueError:
        customer_id = None

    if customer_id is not None:
        customer = (
            db.execute(
                select(Customer)
                .options(selectinload(Customer.supplier))
                .where(Customer.id == customer_id)
            )
            .scalars()
            .first()
        )

    if customer is None:
        customer = (
            db.execute(
                select(Customer)
                .options(selectinload(Customer.supplier))
                .where(Customer.erp_customer_id == identifier)
            )
            .scalars()
            .first()
        )
    if customer is None:
        raise UserServiceError("Customer not found", HTTPStatus.NOT_FOUND)
    if not customer.is_active:
        raise UserServiceError("Customer is disabled", HTTPStatus.BAD_REQUEST)
    return customer


def _resolve_addresses_for_customer(
    db: Session,
    customer: Customer,
    all_addresses: bool,
    provided_ids: Sequence[str],
) -> List[CustomerAddress]:
    stmt = select(CustomerAddress).where(
        CustomerAddress.erp_customer_id == customer.erp_customer_id,
        CustomerAddress.is_active.is_(True),
    )

    if not all_addresses:
        if not provided_ids:
            raise UserServiceError("Address IDs are required when all_addresses is false")
        try:
            ids = [UUID(value) for value in provided_ids]
        except ValueError as exc:  # pragma: no cover - defensive
            raise UserServiceError("Invalid address identifier provided") from exc
        stmt = stmt.where(CustomerAddress.id.in_(ids))

    addresses = db.execute(stmt).scalars().all()

    if not addresses:
        return []

    if not all_addresses:
        requested_ids = {UUID(value) for value in provided_ids}
        found_ids = {addr.id for addr in addresses}
        missing = requested_ids - found_ids
        if missing:
            raise UserServiceError(
                "Unknown customer address ids: " + ", ".join(str(value) for value in missing)
            )

    return addresses


def _derive_supplier(resolved: Sequence[ResolvedCustomerSelection]) -> Supplier:
    supplier_ids = {
        res.customer.supplier_id for res in resolved if res.customer.supplier_id is not None
    }
    if not supplier_ids:
        raise UserServiceError("Customers are not linked to an active supplier")
    if len(supplier_ids) > 1:
        raise UserServiceError("Customers must belong to the same supplier")
    supplier_id = next(iter(supplier_ids))
    for res in resolved:
        supplier = res.customer.supplier
        if supplier is not None and supplier.id == supplier_id:
            return supplier
    raise UserServiceError("Supplier record not available for customers")


def _resolved_from_user(user: User) -> List[ResolvedCustomerSelection]:
    customer_map = {link.customer_id: link.customer for link in user.customer_links if link.customer}
    address_map: dict[UUID, CustomerAddress] = {}
    for link in user.address_links:
        if link.customer_address is not None:
            address_map[link.customer_address_id] = link.customer_address
    assignments: List[ResolvedCustomerSelection] = []
    for customer_id, customer in customer_map.items():
        addresses = [
            addr
            for addr in address_map.values()
            if addr.erp_customer_id == customer.erp_customer_id
        ]
        assignments.append(ResolvedCustomerSelection(customer=customer, addresses=addresses))
    return assignments
def _supplier_info_from_user(user: User) -> Optional[SupplierInfo]:
    for link in user.address_links:
        address = link.customer_address
        if address and address.supplier:
            supplier = address.supplier
            return SupplierInfo(
                id=supplier.id,
                name=supplier.name,
                slug=supplier.slug,
                logo_url=supplier.logo_url,
            )
    return None


def _customers_info_from_user(user: User) -> List[CustomerInfo]:
    seen: set[UUID] = set()
    customer_infos: List[CustomerInfo] = []

    for link in user.customer_links:
        customer = link.customer
        if customer is None or customer.id in seen:
            continue
        seen.add(customer.id)
        addresses: List[AddressInfo] = []
        for addr_link in user.address_links:
            address = addr_link.customer_address
            if address is None:
                continue
            if address.erp_customer_id != customer.erp_customer_id:
                continue
            addresses.append(
                AddressInfo(
                    id=address.id,
                    erp_address_id=address.erp_address_id,
                    label=address.label,
                    pricelist_code=address.pricelist_code,
                    channel_code=address.channel_code,
                )
            )
        customer_infos.append(
            CustomerInfo(
                id=customer.id,
                erp_customer_id=customer.erp_customer_id,
                name=customer.name,
                addresses=addresses,
            )
        )

    return customer_infos


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
