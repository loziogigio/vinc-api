from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from .errors import UserServiceError
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
)


@dataclass(slots=True)
class ResolvedCustomerSelection:
    customer: Customer
    addresses: List[CustomerAddress]


def _user_with_relationships_statement() -> Select[tuple[User]]:
    return (
        select(User)
        .options(
            selectinload(User.supplier),
            selectinload(User.address_links)
            .selectinload(UserAddressLink.customer_address)
            .selectinload(CustomerAddress.customer)
            .selectinload(Customer.supplier),
            selectinload(User.customer_links)
            .selectinload(UserCustomerLink.customer)
            .selectinload(Customer.supplier),
        )
    )


def load_user_with_relations(db: Session, user_id: UUID) -> User:
    stmt: Select[tuple[User]] = (
        _user_with_relationships_statement().where(User.id == user_id)
    )
    user = db.execute(stmt).scalars().unique().one_or_none()
    if user is None:
        raise UserServiceError("User not found")
    return user


def load_user_with_relations_by_kc_id(db: Session, kc_user_id: str) -> User:
    stmt: Select[tuple[User]] = (
        _user_with_relationships_statement().where(User.kc_user_id == kc_user_id)
    )
    user = db.execute(stmt).scalars().unique().one_or_none()
    if user is None:
        raise UserServiceError("User not found")
    return user


def resolve_customer_selections(
    db: Session,
    selections: Sequence[CustomerSelection],
) -> List[ResolvedCustomerSelection]:
    resolved: List[ResolvedCustomerSelection] = []
    seen_customers: set[UUID] = set()
    seen_addresses: set[UUID] = set()

    for selection in selections:
        customer = get_customer_by_identifier(db, selection.customer_id)
        if customer.id in seen_customers:
            raise UserServiceError("Duplicate customer assignment is not allowed")

        addresses = resolve_addresses_for_customer(
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


def get_customer_by_identifier(db: Session, identifier: str) -> Customer:
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
        raise UserServiceError("Customer not found")
    if not customer.is_active:
        raise UserServiceError("Customer is disabled")
    return customer


def resolve_addresses_for_customer(
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


def derive_supplier(resolved: Iterable[ResolvedCustomerSelection]) -> Supplier:
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


def resolved_from_user(user: User) -> List[ResolvedCustomerSelection]:
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


def supplier_info_from_user(user: User) -> Optional[SupplierInfo]:
    # For supplier_admin/supplier_helpdesk, use direct supplier relationship
    if user.supplier:
        return SupplierInfo(
            id=user.supplier.id,
            name=user.supplier.name,
            slug=user.supplier.slug,
            logo_url=user.supplier.logo_url,
        )

    # Check supplier_links first
    if user.supplier_links:
        link = user.supplier_links[0]
        return SupplierInfo(
            id=link.supplier.id,
            name=link.supplier.name,
            slug=link.supplier.slug,
            logo_url=link.supplier.logo_url,
            role=link.role,
        )

    # For other roles, derive from customer relationships
    for link in user.address_links:
        address = link.customer_address
        if address and address.customer and address.customer.supplier:
            supplier = address.customer.supplier
            return SupplierInfo(
                id=supplier.id,
                name=supplier.name,
                slug=supplier.slug,
                logo_url=supplier.logo_url,
            )
    return None


def suppliers_info_from_user(user: User) -> List[SupplierInfo]:
    """Get all suppliers associated with a user, including via supplier_links."""
    seen: set[UUID] = set()
    supplier_infos: List[SupplierInfo] = []

    # Add direct supplier relationship (deprecated, kept for backwards compatibility)
    if user.supplier and user.supplier.id not in seen:
        seen.add(user.supplier.id)
        supplier_infos.append(
            SupplierInfo(
                id=user.supplier.id,
                name=user.supplier.name,
                slug=user.supplier.slug,
                logo_url=user.supplier.logo_url,
            )
        )

    # Add suppliers from supplier_links
    for link in user.supplier_links:
        if link.supplier and link.supplier.id not in seen:
            seen.add(link.supplier.id)
            supplier_infos.append(
                SupplierInfo(
                    id=link.supplier.id,
                    name=link.supplier.name,
                    slug=link.supplier.slug,
                    logo_url=link.supplier.logo_url,
                    role=link.role,
                    status=link.status,
                    is_active=link.is_active,
                )
            )

    return supplier_infos


def customers_info_from_user(user: User) -> List[CustomerInfo]:
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
        # Get supplier info for this customer
        supplier_info = None
        if customer.supplier:
            supplier_info = SupplierInfo(
                id=customer.supplier.id,
                name=customer.supplier.name,
                slug=customer.supplier.slug,
                logo_url=customer.supplier.logo_url,
            )

        customer_infos.append(
            CustomerInfo(
                id=customer.id,
                erp_customer_id=customer.erp_customer_id,
                name=customer.name,
                supplier=supplier_info,
                addresses=addresses,
            )
        )

    return customer_infos


def load_customers_by_ids(
    db: Session,
    identifiers: Sequence[str],
    *,
    expected_supplier_id: Optional[UUID] = None,
) -> List[Customer]:
    if not identifiers:
        return []
    try:
        ids = [UUID(value) for value in identifiers]
    except ValueError as exc:
        raise UserServiceError("Invalid customer identifier in memberships") from exc
    stmt = select(Customer).where(Customer.id.in_(ids))
    customers = db.execute(stmt).scalars().all()
    found = {customer.id for customer in customers}
    missing = {uuid for uuid in ids if uuid not in found}
    if missing:
        raise UserServiceError(
            "Unknown customer ids in memberships: " + ", ".join(str(value) for value in missing)
        )
    if expected_supplier_id is not None:
        for customer in customers:
            if customer.supplier_id != expected_supplier_id:
                raise UserServiceError("Customer not linked to supplier scope")
    return customers


def load_addresses_by_ids(
    db: Session,
    identifiers: Sequence[str],
    *,
    expected_supplier_id: Optional[UUID] = None,
) -> List[CustomerAddress]:
    if not identifiers:
        return []
    try:
        ids = [UUID(value) for value in identifiers]
    except ValueError as exc:
        raise UserServiceError("Invalid address identifier in memberships") from exc
    stmt = select(CustomerAddress).options(selectinload(CustomerAddress.customer)).where(CustomerAddress.id.in_(ids))
    addresses = db.execute(stmt).scalars().all()
    found = {address.id for address in addresses}
    missing = {uuid for uuid in ids if uuid not in found}
    if missing:
        raise UserServiceError(
            "Unknown address ids in memberships: " + ", ".join(str(value) for value in missing)
        )
    if expected_supplier_id is not None:
        for address in addresses:
            if address.customer and address.customer.supplier_id != expected_supplier_id:
                raise UserServiceError("Address not linked to supplier scope")
    return addresses
