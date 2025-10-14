from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...api.deps import (
    get_db,
    get_request_user_sub,
    get_settings_dep,
    require_roles,
)
from ...core.config import Settings
from ..users.errors import UserServiceError
from ..users.service import get_user_by_kc_id
from ..permissions.service import list_suppliers_from_memberships, MembershipDoc, load_membership_doc
from ...core.mongo import get_mongo_db
from .schemas import SupplierCreate, SupplierResponse, SupplierUpdate
from .service import (
    create_supplier,
    list_suppliers,
    list_suppliers_for_user,
    serialize_supplier,
    serialize_suppliers,
    update_supplier,
    get_supplier,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("/", response_model=List[SupplierResponse])
def list_suppliers_endpoint(
    include_inactive: bool = Query(True, description="Include inactive suppliers"),
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("super_admin")),
) -> List[SupplierResponse]:
    suppliers = list_suppliers(db, include_inactive=include_inactive)
    return serialize_suppliers(suppliers)


@router.post("/", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier_endpoint(
    payload: SupplierCreate,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("super_admin")),
) -> SupplierResponse:
    try:
        supplier = create_supplier(db, payload)
    except UserServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail)
    return serialize_supplier(supplier)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
def update_supplier_endpoint(
    supplier_id: UUID,
    payload: SupplierUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("super_admin")),
) -> SupplierResponse:
    try:
        supplier = update_supplier(db, supplier_id, payload)
    except UserServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.detail)
    return serialize_supplier(supplier)


@router.get("/me", response_model=List[SupplierResponse])
async def list_my_suppliers(
    db: Session = Depends(get_db),
    kc_user_id: str = Depends(get_request_user_sub),
) -> List[SupplierResponse]:
    suppliers = list_suppliers_for_user(db, kc_user_id)
    if suppliers:
        return serialize_suppliers(suppliers)

    # As a fallback for super admins without address links, expose all suppliers.
    user = get_user_by_kc_id(db, kc_user_id)
    if user.role == "super_admin":
        return serialize_suppliers(list_suppliers(db, include_inactive=True))

    # Use memberships (Mongo) when present to list suppliers scoped to user
    mongo = get_mongo_db()
    if mongo is not None:
        mdoc = await load_membership_doc(kc_user_id)
        if mdoc is not None:
            msuppliers = list_suppliers_from_memberships(db, mdoc)
            if msuppliers:
                return serialize_suppliers(msuppliers)
    return []


@router.get("/{supplier_id}", response_model=SupplierResponse)
def get_supplier_endpoint(
    supplier_id: UUID,
    db: Session = Depends(get_db),
    _: str = Depends(require_roles("super_admin")),
) -> SupplierResponse:
    try:
        supplier = get_supplier(db, supplier_id)
    except UserServiceError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.detail)
    return serialize_supplier(supplier)
