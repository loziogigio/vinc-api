from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ...api.deps import (
    get_allowed_address_ids,
    get_allowed_customer_ids,
    get_db,
    get_request_user_role,
    require_roles,
)
from .schemas import (
    CustomerAddressCreate,
    CustomerAddressResponse,
    CustomerAddressUpdate,
    CustomerCreate,
    CustomerDetailResponse,
    CustomerResponse,
    CustomerUpdate,
)
from .service import (
    CustomerServiceError,
    create_customer,
    create_customer_address,
    delete_customer,
    delete_customer_address,
    get_customer,
    get_customer_address,
    list_customer_addresses,
    list_customers,
    serialize_customer,
    serialize_customer_address,
    serialize_customer_addresses,
    serialize_customers,
    update_customer,
    update_customer_address,
)


router = APIRouter(prefix="/customers", tags=["customers"])


def _get_tenant_supplier_id(request: Request) -> UUID | None:
    tenant_raw = getattr(request.state, "tenant_id", None)
    if tenant_raw in (None, ""):
        return None
    try:
        return UUID(str(tenant_raw))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Tenant-ID header",
        ) from exc


def _is_allowed_for_supplier_team(request: Request, supplier_id: UUID, db: Session) -> bool:
    """
    Database check: Is this user allowed to access this supplier team?

    Queries user_supplier_link table to verify user has an active link to the supplier.

    Returns True if:
    - User is super_admin (can access any supplier), OR
    - user has an active link in user_supplier_link with status='active' and is_active=True
    """
    user_role = getattr(request.state, "user_role", "").lower()
    if user_role == "super_admin":
        return True

    user_sub = getattr(request.state, "user_sub", None)
    if not user_sub:
        return False

    # Query database for user and check supplier link
    from ..users.models import User, UserSupplierLink

    user = db.query(User).filter(User.kc_user_id == user_sub).first()
    if not user:
        return False

    # Check if user has active link to the supplier
    link = db.query(UserSupplierLink).filter(
        UserSupplierLink.user_id == user.id,
        UserSupplierLink.supplier_id == supplier_id,
        UserSupplierLink.status == "active",
        UserSupplierLink.is_active == True
    ).first()

    return link is not None


def _require_tenant_scope(request: Request, *, is_super_admin: bool, db: Session) -> UUID | None:
    """
    Validate and return the tenant supplier ID.

    SECURITY: Validates that X-Tenant-ID matches user's authorized suppliers by querying database.
    Simple answer: is_allowed?
    """
    tenant_supplier_id = _get_tenant_supplier_id(request)

    if is_super_admin:
        return tenant_supplier_id

    # Require X-Tenant-ID
    if tenant_supplier_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header required",
        )

    # Database check: is_allowed?
    if not _is_allowed_for_supplier_team(request, tenant_supplier_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Not authorized for this supplier team",
        )

    return tenant_supplier_id


def _ensure_customer_scope(
    customer_supplier_id: UUID,
    tenant_supplier_id: UUID | None,
    *,
    is_super_admin: bool,
) -> None:
    if not is_super_admin and tenant_supplier_id and customer_supplier_id != tenant_supplier_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer not available for current tenant",
        )


@router.get("/", response_model=List[CustomerDetailResponse])
def list_customers_endpoint(
    request: Request,
    include_inactive: bool = Query(False, description="Include inactive customers"),
    include_inactive_addresses: bool = Query(False, description="Include inactive addresses"),
    supplier_id: UUID | None = Query(None, description="Filter by supplier"),
    search: str | None = Query(None, description="Search by name, code, VAT, fiscal code, email"),
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    allowed_addresses: List[str] = Depends(get_allowed_address_ids),
) -> List[CustomerDetailResponse]:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"

    # Determine if user has supplier-level access (no need for individual customer filtering)
    # Super admins and supplier admins see all customers in their scope
    has_supplier_level_access = is_super_admin or is_supplier_admin

    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    effective_supplier_id = supplier_id if supplier_id is not None else tenant_supplier_id

    # Only pass allowed_customer_ids for users who need customer-level filtering
    # Supplier admins see ALL customers in their supplier (no individual filtering)
    customers = list_customers(
        db,
        include_inactive=include_inactive,
        supplier_id=effective_supplier_id,
        search=search,
        allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
        is_admin=has_supplier_level_access,
    )
    return serialize_customers(
        customers,
        include_addresses=True,
        allowed_address_ids=None if has_supplier_level_access else allowed_addresses,
        include_inactive_addresses=include_inactive_addresses or has_supplier_level_access,
    )


@router.post("/", response_model=CustomerDetailResponse, status_code=status.HTTP_201_CREATED)
def create_customer_endpoint(
    payload: CustomerCreate,
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    _: str = Depends(require_roles("super_admin", "wholesale_admin", "supplier_admin")),
) -> CustomerDetailResponse:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    if not is_super_admin:
        _ensure_customer_scope(
            payload.supplier_id,
            tenant_supplier_id,
            is_super_admin=is_super_admin,
        )

    try:
        customer = create_customer(db, payload)
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_customer(customer, include_addresses=True, allowed_address_ids=None)


@router.get("/{customer_id}", response_model=CustomerDetailResponse)
def get_customer_endpoint(
    customer_id: UUID,
    request: Request,
    include_inactive_addresses: bool = Query(False, description="Include inactive addresses"),
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    allowed_addresses: List[str] = Depends(get_allowed_address_ids),
) -> CustomerDetailResponse:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"

    # Supplier admins have supplier-level access (no customer ID filtering needed)
    has_supplier_level_access = is_super_admin or is_supplier_admin

    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)

    _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)

    return serialize_customer(
        customer,
        include_addresses=True,
        allowed_address_ids=None if has_supplier_level_access else allowed_addresses,
        include_inactive_addresses=include_inactive_addresses or has_supplier_level_access,
    )


@router.patch("/{customer_id}", response_model=CustomerDetailResponse)
def update_customer_endpoint(
    customer_id: UUID,
    payload: CustomerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    _: str = Depends(require_roles("super_admin", "wholesale_admin", "supplier_admin")),
) -> CustomerDetailResponse:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"
    has_supplier_level_access = is_super_admin or is_supplier_admin

    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
        _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)
        customer = update_customer(db, customer, payload)
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_customer(customer, include_addresses=True, allowed_address_ids=None)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer_endpoint(
    customer_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    _: str = Depends(require_roles("super_admin", "wholesale_admin", "supplier_admin")),
) -> None:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"
    has_supplier_level_access = is_super_admin or is_supplier_admin

    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
        _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)
        delete_customer(db, customer)
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)


@router.get("/{customer_id}/addresses", response_model=List[CustomerAddressResponse])
def list_addresses_endpoint(
    customer_id: UUID,
    request: Request,
    include_inactive: bool = Query(False, description="Include inactive addresses"),
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    allowed_addresses: List[str] = Depends(get_allowed_address_ids),
) -> List[CustomerAddressResponse]:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"
    has_supplier_level_access = is_super_admin or is_supplier_admin

    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)

    _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)

    addresses = list_customer_addresses(
        customer,
        include_inactive=include_inactive or has_supplier_level_access,
        allowed_address_ids=None if has_supplier_level_access else allowed_addresses,
        is_admin=has_supplier_level_access,
    )
    return serialize_customer_addresses(addresses)


@router.post(
    "/{customer_id}/addresses",
    response_model=CustomerAddressResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_address_endpoint(
    customer_id: UUID,
    payload: CustomerAddressCreate,
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    _: str = Depends(require_roles("super_admin", "wholesale_admin", "supplier_admin")),
)  -> CustomerAddressResponse:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"
    has_supplier_level_access = is_super_admin or is_supplier_admin

    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
        _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)
        address = create_customer_address(db, customer, payload)
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_customer_address(address)


@router.get(
    "/{customer_id}/addresses/{address_id}",
    response_model=CustomerAddressResponse,
)
def get_address_endpoint(
    customer_id: UUID,
    address_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    allowed_addresses: List[str] = Depends(get_allowed_address_ids),
) -> CustomerAddressResponse:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"
    has_supplier_level_access = is_super_admin or is_supplier_admin
    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
        address = get_customer_address(
            db,
            customer,
            address_id,
            allowed_address_ids=None if has_supplier_level_access else allowed_addresses,
            is_admin=has_supplier_level_access,
        )
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)

    _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)
    return serialize_customer_address(address)


@router.patch(
    "/{customer_id}/addresses/{address_id}",
    response_model=CustomerAddressResponse,
)
def update_address_endpoint(
    customer_id: UUID,
    address_id: UUID,
    payload: CustomerAddressUpdate,
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    allowed_addresses: List[str] = Depends(get_allowed_address_ids),
    _: str = Depends(require_roles("super_admin", "wholesale_admin", "supplier_admin")),
) -> CustomerAddressResponse:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"
    has_supplier_level_access = is_super_admin or is_supplier_admin
    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
        _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)
        address = get_customer_address(
            db,
            customer,
            address_id,
            allowed_address_ids=[] if has_supplier_level_access else allowed_addresses,
            is_admin=has_supplier_level_access,
        )
        address = update_customer_address(db, address, payload)
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_customer_address(address)


@router.delete("/{customer_id}/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address_endpoint(
    customer_id: UUID,
    address_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    role: str | None = Depends(get_request_user_role),
    allowed_customers: List[str] = Depends(get_allowed_customer_ids),
    allowed_addresses: List[str] = Depends(get_allowed_address_ids),
    _: str = Depends(require_roles("super_admin", "wholesale_admin", "supplier_admin")),
) -> None:
    role_lower = (role or "").lower()
    is_super_admin = role_lower == "super_admin"
    is_supplier_admin = role_lower == "supplier_admin"
    has_supplier_level_access = is_super_admin or is_supplier_admin
    tenant_supplier_id = _require_tenant_scope(request, is_super_admin=is_super_admin, db=db)
    try:
        customer = get_customer(
            db,
            customer_id,
            allowed_customer_ids=None if has_supplier_level_access else allowed_customers,
            is_admin=has_supplier_level_access,
        )
        _ensure_customer_scope(customer.supplier_id, tenant_supplier_id, is_super_admin=is_super_admin)
        address = get_customer_address(
            db,
            customer,
            address_id,
            allowed_address_ids=[] if has_supplier_level_access else allowed_addresses,
            is_admin=has_supplier_level_access,
        )
        delete_customer_address(db, address)
    except CustomerServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)


__all__ = [
    "router",
]
