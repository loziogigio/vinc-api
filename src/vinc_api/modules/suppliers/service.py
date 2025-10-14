from __future__ import annotations

import re
from typing import List, Optional
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...modules.users.models import (
    Customer,
    CustomerAddress,
    Supplier,
    User,
    UserAddressLink,
)
from ...modules.users.errors import UserServiceError
from .schemas import SupplierCreate, SupplierResponse, SupplierUpdate


SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def list_suppliers(db: Session, *, include_inactive: bool = True) -> List[Supplier]:
    stmt: Select[tuple[Supplier]] = select(Supplier)
    if not include_inactive:
        stmt = stmt.where(Supplier.is_active.is_(True))
    stmt = stmt.order_by(Supplier.name.asc())
    return db.execute(stmt).scalars().all()


def get_supplier(db: Session, supplier_id: UUID) -> Supplier:
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise UserServiceError("Supplier not found")
    return supplier


def create_supplier(db: Session, payload: SupplierCreate) -> Supplier:
    slug = payload.slug or _slugify(payload.name)
    supplier = Supplier(
        name=payload.name,
        slug=slug,
        logo_url=payload.logo_url,
        legal_name=payload.legal_name,
        legal_address=payload.legal_address,
        legal_details=payload.legal_details,
        legal_email=payload.legal_email,
        legal_number=payload.legal_number,
        tax_id=payload.tax_id,
        status=payload.status or "active",
        is_active=payload.is_active if payload.is_active is not None else True,
    )
    db.add(supplier)
    try:
        db.flush()
    except IntegrityError as exc:
        raise UserServiceError("Supplier slug already exists") from exc
    return supplier


def update_supplier(db: Session, supplier_id: UUID, payload: SupplierUpdate) -> Supplier:
    supplier = get_supplier(db, supplier_id)
    if payload.name is not None:
        supplier.name = payload.name
    if payload.slug is not None:
        supplier.slug = payload.slug or _slugify(supplier.name)
    if payload.logo_url is not None:
        supplier.logo_url = payload.logo_url
    if payload.legal_name is not None:
        supplier.legal_name = payload.legal_name
    if payload.legal_address is not None:
        supplier.legal_address = payload.legal_address
    if payload.legal_details is not None:
        supplier.legal_details = payload.legal_details
    if payload.legal_email is not None:
        supplier.legal_email = payload.legal_email
    if payload.legal_number is not None:
        supplier.legal_number = payload.legal_number
    if payload.tax_id is not None:
        supplier.tax_id = payload.tax_id
    if payload.status is not None:
        supplier.status = payload.status
    if payload.is_active is not None:
        supplier.is_active = payload.is_active
    try:
        db.flush()
    except IntegrityError as exc:
        raise UserServiceError("Supplier slug already exists") from exc
    return supplier


def list_suppliers_for_user(db: Session, kc_user_id: str) -> List[Supplier]:
    stmt = (
        select(Supplier)
        .join(Customer, Customer.supplier_id == Supplier.id)
        .join(CustomerAddress, CustomerAddress.customer_id == Customer.id)
        .join(UserAddressLink, UserAddressLink.customer_address_id == CustomerAddress.id)
        .join(User, User.id == UserAddressLink.user_id)
        .where(User.kc_user_id == kc_user_id)
        .distinct()
        .order_by(Supplier.name.asc())
    )
    return db.execute(stmt).scalars().all()


def serialize_supplier(supplier: Supplier) -> SupplierResponse:
    return SupplierResponse.model_validate(supplier)


def serialize_suppliers(suppliers: List[Supplier]) -> List[SupplierResponse]:
    return [serialize_supplier(supplier) for supplier in suppliers]


def _slugify(name: str) -> str:
    slug = SLUG_PATTERN.sub("-", name.lower()).strip("-")
    return slug or "supplier"
