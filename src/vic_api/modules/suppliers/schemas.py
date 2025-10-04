from __future__ import annotations

from typing import Optional
from uuid import UUID

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover
    class BaseModel:  # type: ignore
        pass

    def Field(*args, **kwargs):  # type: ignore
        return kwargs.get("default")


class SupplierBase(BaseModel):
    name: str = Field(..., examples=["DFL S.r.l."])
    slug: Optional[str] = Field(default=None, description="URL-friendly identifier")
    logo_url: Optional[str] = None
    legal_name: Optional[str] = None
    legal_address: Optional[str] = None
    legal_details: Optional[str] = None
    is_active: Optional[bool] = True


class SupplierCreate(SupplierBase):
    pass


class SupplierUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    logo_url: Optional[str] = None
    legal_name: Optional[str] = None
    legal_address: Optional[str] = None
    legal_details: Optional[str] = None
    is_active: Optional[bool] = None


class SupplierResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    logo_url: Optional[str]
    legal_name: Optional[str]
    legal_address: Optional[str]
    legal_details: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True
