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
    SUPER_ADMIN = "super_admin"


class UserStatus(str, Enum):
    INVITED = "invited"
    ACTIVE = "active"
    DISABLED = "disabled"


class CustomerSelection(BaseModel):
    customer_id: str
    all_addresses: bool = False
    address_ids: Optional[List[str]] = None


class UserCreateRequest(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    role: UserRole
    customers: List[CustomerSelection]
    send_invite: bool = False


class UserUpdateRequest(BaseModel):
    role: Optional[UserRole] = None
    customers: Optional[List[CustomerSelection]] = None


class SupplierInfo(BaseModel):
    id: UUID
    name: str
    slug: Optional[str]
    logo_url: Optional[str]


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
    supplier: Optional[SupplierInfo]
    customers: List[CustomerInfo]
    created_at: datetime
    updated_at: datetime


class UserMeResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: Optional[str]
    role: UserRole
    supplier: Optional[SupplierInfo]
    customers: List[CustomerInfo]
    addresses: List[AddressInfo]

