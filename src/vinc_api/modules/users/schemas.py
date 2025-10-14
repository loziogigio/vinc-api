from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

try:  # Prefer pydantic v2
    from pydantic import BaseModel, EmailStr
except Exception:  # pragma: no cover - fallback when pydantic missing
    class BaseModel:  # type: ignore
        pass

    EmailStr = str  # type: ignore


class UserRole(str, Enum):
    RESELLER = "reseller"
    AGENT = "agent"
    VIEWER = "viewer"
    WHOLESALE_ADMIN = "wholesale_admin"
    WHOLESALER_HELPDESK = "wholesaler_helpdesk"
    SUPPLIER_ADMIN = "supplier_admin"
    SUPPLIER_HELPDESK = "supplier_helpdesk"
    SUPER_ADMIN = "super_admin"


class UserStatus(str, Enum):
    INVITED = "invited"
    ACTIVE = "active"
    DISABLED = "disabled"


class CustomerSelection(BaseModel):
    customer_id: str
    all_addresses: bool = False
    address_ids: Optional[List[str]] = None


class SupplierSelection(BaseModel):
    supplier_id: str
    role: str = "viewer"  # admin, helpdesk, viewer


class MembershipEntry(BaseModel):
    scope_type: str
    scope_id: Optional[str] = None
    role: Optional[str] = None
    capabilities: Optional[List[str]] = None
    reseller_scope: Optional[str] = None
    reseller_account_ids: Optional[List[str]] = None
    address_scope: Optional[str] = None
    address_ids: Optional[List[str]] = None
    limits: Optional[dict] = None
    flags: Optional[dict] = None
    metadata: Optional[dict] = None


class Memberships(BaseModel):
    user_key: Optional[str] = None
    default_role: Optional[str] = None
    memberships: List[MembershipEntry] = []


class UserCreateRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    role: Optional[UserRole] = None
    suppliers: Optional[List[SupplierSelection]] = None
    customers: Optional[List[CustomerSelection]] = None
    memberships: Optional[Memberships] = None
    send_invite: bool = False


class UserUpdateRequest(BaseModel):
    role: Optional[UserRole] = None
    suppliers: Optional[List[SupplierSelection]] = None
    customers: Optional[List[CustomerSelection]] = None
    memberships: Optional[Memberships] = None


class SupplierInfo(BaseModel):
    id: UUID
    name: str
    slug: Optional[str]
    logo_url: Optional[str]
    role: Optional[str] = None  # Role within the supplier (from user_supplier_link: admin, helpdesk, viewer)
    status: Optional[str] = None  # Link status (from user_supplier_link: pending, active, suspended, revoked)
    is_active: Optional[bool] = None  # Link active flag (from user_supplier_link)


class AddressInfo(BaseModel):
    id: UUID
    erp_address_id: str
    label: Optional[str]
    pricelist_code: Optional[str]
    channel_code: Optional[str]


class CustomerInfo(BaseModel):
    id: UUID
    erp_customer_id: str
    name: Optional[str]
    supplier: Optional[SupplierInfo]
    addresses: List[AddressInfo]


class UserCreatedResponse(BaseModel):
    id: UUID
    email: EmailStr
    status: UserStatus


class UserDetailResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: Optional[str]
    role: UserRole
    status: UserStatus
    kc_user_id: Optional[str]
    supplier: Optional[SupplierInfo]  # Deprecated: kept for backwards compatibility
    suppliers: List[SupplierInfo] = []  # New field: list of all associated suppliers
    customers: List[CustomerInfo]
    created_at: datetime
    updated_at: datetime
    memberships: Optional[Memberships] = None


class UserListItemResponse(BaseModel):
    """User list item with link counts (for table view)"""
    id: UUID
    email: EmailStr
    name: Optional[str]
    role: UserRole
    status: UserStatus
    supplier_count: int = 0  # Number of supplier links
    customer_count: int = 0  # Number of customer links
    address_count: int = 0   # Number of address links
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """Paginated user list response"""
    items: List[UserListItemResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class UserMeResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: Optional[str]
    role: UserRole
    supplier: Optional[SupplierInfo]  # Deprecated: kept for backwards compatibility
    suppliers: List[SupplierInfo] = []  # New field: list of all associated suppliers
    customers: List[CustomerInfo]
    addresses: List[AddressInfo]
    memberships: Optional[Memberships] = None
