from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from typing import Iterable, List, Optional, Sequence, Set
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..users.models import Customer, CustomerAddress, Supplier
from .schemas import (
    CustomerAddressCreate,
    CustomerAddressResponse,
    CustomerAddressUpdate,
    CustomerCreate,
    CustomerDetailResponse,
    CustomerResponse,
    CustomerUpdate,
)


@dataclass(slots=True)
class CustomerServiceError(Exception):
    detail: str
    status_code: HTTPStatus = HTTPStatus.BAD_REQUEST

    def __str__(self) -> str:  # pragma: no cover
        return self.detail


# Accept both legacy and new admin role names
ADMIN_ROLES = {"super_admin", "wholesale_admin", "supplier_admin"}


def list_customers(
    db: Session,
    *,
    include_inactive: bool,
    supplier_id: Optional[UUID],
    search: Optional[str],
    allowed_customer_ids: Sequence[str] | None,
    is_admin: bool,
) -> List[Customer]:
    stmt: Select[tuple[Customer]] = (
        select(Customer)
        .options(selectinload(Customer.addresses))
        .order_by(Customer.erp_customer_id.asc())
    )
    if supplier_id:
        stmt = stmt.where(Customer.supplier_id == supplier_id)
    if not include_inactive:
        stmt = stmt.where(Customer.is_active.is_(True))

    # Add search filter
    if search:
        search_term = f"%{search}%"
        stmt = stmt.where(
            (Customer.name.ilike(search_term)) |
            (Customer.business_name.ilike(search_term)) |
            (Customer.public_customer_code.ilike(search_term)) |
            (Customer.customer_code.ilike(search_term)) |
            (Customer.erp_customer_id.ilike(search_term)) |
            (Customer.vat_number.ilike(search_term)) |
            (Customer.fiscal_code.ilike(search_term)) |
            (Customer.contact_email.ilike(search_term))
        )

    # Apply access control filters for non-admin users
    if not is_admin:
        # If supplier_id is already provided, it scopes the results to that supplier
        # This is more efficient than filtering by 1000+ customer IDs
        # Only use allowed_customer_ids filter if NO supplier_id scope exists
        if not supplier_id:
            # No supplier scope - must filter by individual customer IDs
            allowed_uuid = _parse_uuid_set(allowed_customer_ids)
            if not allowed_uuid:
                return []
            stmt = stmt.where(Customer.id.in_(allowed_uuid))
        # else: supplier_id filter already applied, no need for customer ID filter
        # This handles supplier_admin and supplier_helpdesk roles efficiently

    return db.execute(stmt).scalars().unique().all()


def get_customer(
    db: Session,
    customer_id: UUID,
    *,
    allowed_customer_ids: Sequence[str] | None,
    is_admin: bool,
) -> Customer:
    stmt = (
        select(Customer)
        .options(selectinload(Customer.addresses))
        .where(Customer.id == customer_id)
    )
    customer = db.execute(stmt).scalars().unique().one_or_none()
    if customer is None:
        raise CustomerServiceError("Customer not found", HTTPStatus.NOT_FOUND)
    if not is_admin and str(customer.id) not in set(allowed_customer_ids or []):
        raise CustomerServiceError("Customer access denied", HTTPStatus.FORBIDDEN)
    return customer


def create_customer(db: Session, payload: CustomerCreate) -> Customer:
    supplier = db.get(Supplier, payload.supplier_id)
    if supplier is None:
        raise CustomerServiceError("Supplier not found", HTTPStatus.NOT_FOUND)

    customer = Customer(
        supplier_id=payload.supplier_id,
        erp_customer_id=payload.erp_customer_id,
        name=payload.name,
        is_active=payload.is_active if payload.is_active is not None else True,
    )
    db.add(customer)
    try:
        db.flush()
    except IntegrityError as exc:
        raise CustomerServiceError("Customer already exists", HTTPStatus.CONFLICT) from exc
    return customer


def update_customer(db: Session, customer: Customer, payload: CustomerUpdate) -> Customer:
    # Update fields if provided in payload (using model_dump to get all fields)
    payload_dict = payload.model_dump(exclude_unset=True)

    for field, value in payload_dict.items():
        if hasattr(customer, field):
            setattr(customer, field, value)

    try:
        db.flush()
    except IntegrityError as exc:
        raise CustomerServiceError("Customer already exists", HTTPStatus.CONFLICT) from exc
    return customer


def delete_customer(db: Session, customer: Customer) -> None:
    db.delete(customer)
    db.flush()


def list_customer_addresses(
    customer: Customer,
    *,
    include_inactive: bool,
    allowed_address_ids: Sequence[str] | None,
    is_admin: bool,
) -> List[CustomerAddress]:
    if is_admin:
        allowed: Optional[Set[str]] = None
    elif allowed_address_ids is None:
        return []
    else:
        allowed = {str(value) for value in allowed_address_ids}

    results: List[CustomerAddress] = []
    for address in sorted(customer.addresses, key=lambda addr: addr.label or addr.erp_address_id):
        if not include_inactive and not address.is_active:
            continue
        if allowed is not None and str(address.id) not in allowed:
            continue
        results.append(address)
    return results


def create_customer_address(
    db: Session,
    customer: Customer,
    payload: CustomerAddressCreate,
) -> CustomerAddress:
    # Get all payload fields except those we handle specially
    payload_dict = payload.model_dump(exclude_unset=True)

    # Set required fields
    payload_dict['customer_id'] = customer.id
    payload_dict['erp_customer_id'] = customer.erp_customer_id

    # Ensure is_active has a default
    if 'is_active' not in payload_dict:
        payload_dict['is_active'] = True

    address = CustomerAddress(**payload_dict)
    db.add(address)
    try:
        db.flush()
    except IntegrityError as exc:
        raise CustomerServiceError("Address already exists", HTTPStatus.CONFLICT) from exc
    return address


def get_customer_address(
    db: Session,
    customer: Customer,
    address_id: UUID,
    *,
    allowed_address_ids: Sequence[str] | None,
    is_admin: bool,
) -> CustomerAddress:
    address = db.get(CustomerAddress, address_id)
    if address is None or address.erp_customer_id != customer.erp_customer_id:
        raise CustomerServiceError("Customer address not found", HTTPStatus.NOT_FOUND)

    if not is_admin and str(address.id) not in set(allowed_address_ids or []):
        raise CustomerServiceError("Address access denied", HTTPStatus.FORBIDDEN)
    return address


def update_customer_address(
    db: Session,
    address: CustomerAddress,
    payload: CustomerAddressUpdate,
) -> CustomerAddress:
    # Update fields if provided in payload (using model_dump to get all fields)
    payload_dict = payload.model_dump(exclude_unset=True)

    for field, value in payload_dict.items():
        if hasattr(address, field):
            setattr(address, field, value)

    db.flush()
    return address


def delete_customer_address(db: Session, address: CustomerAddress) -> None:
    db.delete(address)
    db.flush()


def serialize_customer(
    customer: Customer,
    *,
    include_addresses: bool,
    allowed_address_ids: Optional[Iterable[str]] = None,
    include_inactive_addresses: bool = True,
) -> CustomerDetailResponse | CustomerResponse:
    if not include_addresses:
        return CustomerResponse.model_validate(customer)

    allowed = set(allowed_address_ids or []) if allowed_address_ids is not None else None
    addresses = []
    for address in sorted(customer.addresses, key=lambda addr: addr.label or addr.erp_address_id):
        if not include_inactive_addresses and not address.is_active:
            continue
        if allowed is not None and str(address.id) not in allowed:
            continue
        addresses.append(serialize_customer_address(address))

    # Use model_validate to automatically map all fields from the ORM model
    customer_dict = CustomerDetailResponse.model_validate(customer).model_dump()
    customer_dict['addresses'] = addresses
    return CustomerDetailResponse(**customer_dict)


def serialize_customers(
    customers: Sequence[Customer],
    *,
    include_addresses: bool,
    allowed_address_ids: Optional[Iterable[str]] = None,
    include_inactive_addresses: bool = True,
) -> List[CustomerDetailResponse | CustomerResponse]:
    return [
        serialize_customer(
            customer,
            include_addresses=include_addresses,
            allowed_address_ids=allowed_address_ids,
            include_inactive_addresses=include_inactive_addresses,
        )
        for customer in customers
    ]


def serialize_customer_address(address: CustomerAddress) -> CustomerAddressResponse:
    # Use model_validate to automatically map all fields from the ORM model
    return CustomerAddressResponse.model_validate(address)


def serialize_customer_addresses(addresses: Sequence[CustomerAddress]) -> List[CustomerAddressResponse]:
    return [serialize_customer_address(address) for address in addresses]


def _parse_uuid_set(values: Sequence[str] | None) -> Set[UUID]:
    result: Set[UUID] = set()
    if not values:
        return result
    for value in values:
        try:
            result.add(UUID(value))
        except (ValueError, TypeError):
            continue
    return result
