from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from sqlalchemy.orm import Session

from ...api.deps import (
    get_db,
    get_keycloak_admin_dep,
    get_request_user_sub,
    get_settings_dep,
    get_redis_dep,
    require_roles,
)
from ...core.config import Settings
from .schemas import (
    UserCreatedResponse,
    UserCreateRequest,
    UserDetailResponse,
    UserListResponse,
    UserMeResponse,
    UserUpdateRequest,
)
from .errors import UserServiceError
from .service import (
    create_user,
    get_user,
    get_user_by_kc_id,
    list_users,
    list_users_paginated,
    serialize_user_created,
    serialize_user_detail,
    serialize_user_list_item,
    serialize_user_me,
    serialize_users,
    update_user,
)
from ..permissions.service import MembershipDoc, load_membership_doc, persist_membership_doc
from ...core.mongo import get_mongo_db
from .supplier_links_router import router as supplier_links_router
from .customer_links_router import router as customer_links_router
from .address_links_router import router as address_links_router

# Business-facing endpoints coordinating user records and Keycloak state.
router = APIRouter(prefix="/users", tags=["users"])

# Include link management routers
router.include_router(supplier_links_router, tags=["user-supplier-links"])
router.include_router(customer_links_router, tags=["user-customer-links"])
router.include_router(address_links_router, tags=["user-address-links"])


@router.get("/", response_model=UserListResponse)
def list_users_endpoint(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page (1-100)"),
    search: str | None = Query(None, description="Search by email, name, or role"),
    role: str | None = Query(None, description="Filter by role"),
    status: str | None = Query(None, description="Filter by status"),
    supplier_id: UUID | None = Query(None, description="Filter by supplier (super_admin only)"),
    request: Request = None,
    db: Session = Depends(get_db),
    user_role: str = Depends(require_roles("supplier_admin", "super_admin")),
) -> UserListResponse:
    """
    List users with pagination, search, and filters.

    Role-based access control:
    - Super admins: Can filter by supplier_id query parameter OR see all users globally
    - Supplier admins: MUST use X-Tenant-ID header, cannot use supplier_id parameter

    Returns user list with link counts for efficient table display.
    """
    # Get the authenticated user's role
    is_super_admin = user_role == "super_admin"

    # Determine the effective supplier filter based on role
    effective_supplier_id = None

    if is_super_admin:
        # Super admin can use supplier_id query parameter to filter
        # If not provided, they see all users globally
        effective_supplier_id = supplier_id
    else:
        # Supplier admin MUST use X-Tenant-ID and cannot override with supplier_id
        # Reject if supplier_id query parameter is provided
        if supplier_id is not None:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Supplier admins cannot filter by supplier_id. Use X-Tenant-ID header instead."
            )

        # Get tenant ID from X-Tenant-ID header
        tenant_id = getattr(request.state, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID header is required for supplier admins"
            )

        try:
            effective_supplier_id = UUID(tenant_id)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Tenant-ID format"
            )

        # SECURITY: Validate X-Tenant-ID against user_supplier_link table
        # This prevents supplier admins from accessing other suppliers' users by changing the header
        user_sub = getattr(request.state, "user_sub", None)
        if not user_sub:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Access denied: User identity not found"
            )

        # Query database for user and check supplier link
        from .models import User, UserSupplierLink
        current_user = db.query(User).filter(User.kc_user_id == user_sub).first()
        if not current_user:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Access denied: User not found"
            )

        # Check if user has active link to the supplier
        link = db.query(UserSupplierLink).filter(
            UserSupplierLink.user_id == current_user.id,
            UserSupplierLink.supplier_id == effective_supplier_id,
            UserSupplierLink.status == "active",
            UserSupplierLink.is_active == True
        ).first()

        if not link:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Access denied: Not authorized for this supplier team"
            )

    users, total = list_users_paginated(
        db,
        page=page,
        page_size=page_size,
        search=search,
        role_filter=role,
        status_filter=status,
        supplier_id=effective_supplier_id,
    )

    # Calculate total pages
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    # Serialize users with link counts
    items = [serialize_user_list_item(user) for user in users]

    return UserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# Super admins and supplier admins may provision users; Keycloak client is optional in tests.
@router.post("/", response_model=UserCreatedResponse, status_code=http_status.HTTP_201_CREATED)
def create_user_endpoint(
    payload: UserCreateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    keycloak_admin=Depends(get_keycloak_admin_dep),
    _: str = Depends(require_roles("supplier_admin", "super_admin")),
) -> UserCreatedResponse:
    try:
        user = create_user(
            db,
            payload,
            settings=settings,
            keycloak_admin=keycloak_admin,
        )
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_created(user)


# Idempotent role/address reassignment with Keycloak attribute sync.
@router.patch("/{user_id}", response_model=UserDetailResponse)
def update_user_endpoint(
    user_id: UUID,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    keycloak_admin=Depends(get_keycloak_admin_dep),
    _: str = Depends(require_roles("supplier_admin", "super_admin")),
) -> UserDetailResponse:
    try:
        user = update_user(
            db,
            user_id,
            payload,
            settings=settings,
            keycloak_admin=keycloak_admin,
        )
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_detail(user)


# Authenticated user context resolved via Keycloak subject header.
@router.get("/me", response_model=UserMeResponse)
async def get_me_endpoint(
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
    settings: Settings = Depends(get_settings_dep),
    redis=Depends(get_redis_dep),
) -> UserMeResponse:
    cache_key = f"user:me:{kc_user_id}"
    if redis is not None:
        cached = await redis.get(cache_key)
        if cached:
            return UserMeResponse.model_validate_json(cached)

    try:
        user = get_user_by_kc_id(db, kc_user_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)

    # Load memberships from Mongo (optional)
    memberships: MembershipDoc | None = None
    mongo = get_mongo_db()
    if mongo is not None:
        memberships = await load_membership_doc(kc_user_id)

    response = serialize_user_me(user)
    if memberships is not None:
        # type: ignore[attr-defined]
        response.memberships = memberships  # pydantic will serialize

    if redis is not None:
        await redis.set(
            cache_key,
            response.model_dump_json(),
            ex=settings.JWT_ME_CACHE_SECONDS,
        )

    return response


# Membership management (admin only)
@router.get("/{user_id}/memberships", response_model=MembershipDoc)
async def get_user_memberships(user_id: UUID, db: Session = Depends(get_db), _: str = Depends(require_roles("supplier_admin", "super_admin"))):
    try:
        user = get_user(db, user_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    mongo = get_mongo_db()
    if mongo is None:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Document database unavailable")
    key = user.kc_user_id or str(user.id)
    doc = await load_membership_doc(key)
    if doc is None:
        return MembershipDoc(user_key=key, default_role=user.role, memberships=[])
    return doc


@router.put("/{user_id}/memberships", response_model=MembershipDoc)
async def put_user_memberships(
    user_id: UUID,
    payload: MembershipDoc = Body(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("supplier_admin", "super_admin")),
):
    try:
        user = get_user(db, user_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)

    mongo = get_mongo_db()
    if mongo is None:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Document database unavailable")

    key = user.kc_user_id or str(user.id)

    doc = MembershipDoc(
        user_key=key,
        default_role=payload.default_role or user.role,
        memberships=payload.memberships or [],
    )
    return await persist_membership_doc(doc)


# Administrative lookup by UUID.
@router.get("/{user_id}", response_model=UserDetailResponse)
def get_user_endpoint(user_id: UUID, db: Session = Depends(get_db)) -> UserDetailResponse:
    try:
        user = get_user(db, user_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_detail(user)


# Customer association management
@router.post("/{user_id}/customers", response_model=UserDetailResponse, status_code=http_status.HTTP_201_CREATED)
def add_user_customer_endpoint(
    user_id: UUID,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("supplier_admin", "super_admin")),
) -> UserDetailResponse:
    """Add a customer association to a user."""
    from .service import add_user_customer_association
    try:
        user = add_user_customer_association(db, user_id, payload)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_detail(user)


@router.patch("/{user_id}/customers/{customer_id}", response_model=UserDetailResponse)
def update_user_customer_endpoint(
    user_id: UUID,
    customer_id: UUID,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("supplier_admin", "super_admin")),
) -> UserDetailResponse:
    """Update a customer association for a user."""
    from .service import update_user_customer_association
    try:
        user = update_user_customer_association(db, user_id, customer_id, payload)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return serialize_user_detail(user)


@router.delete("/{user_id}/customers/{customer_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_user_customer_endpoint(
    user_id: UUID,
    customer_id: UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("supplier_admin", "super_admin")),
):
    """Remove a customer association from a user."""
    from .service import delete_user_customer_association
    try:
        delete_user_customer_association(db, user_id, customer_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=int(exc.status_code), detail=exc.detail)
    return None
