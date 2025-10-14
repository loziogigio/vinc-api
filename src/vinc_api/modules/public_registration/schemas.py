from __future__ import annotations

from datetime import datetime
from typing import Optional

try:  # prefer pydantic v2
    from pydantic import BaseModel, EmailStr, Field
except Exception:  # pragma: no cover - fallback when dependency missing
    class BaseModel:  # type: ignore
        pass

    def Field(*args, **kwargs):  # type: ignore
        return kwargs.get("default")

    EmailStr = str  # type: ignore


class ResellerRegistrationRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: Optional[str] = Field(default=None, min_length=8, max_length=64)
    phone: Optional[str] = Field(default=None, max_length=64)
    invite_code: Optional[str] = Field(default=None, max_length=128)
    wholesale_slug: Optional[str] = Field(default=None, max_length=128)
    locale: Optional[str] = Field(default="it", max_length=8)


class ResellerRegistrationResponse(BaseModel):
    id: str
    keycloak_user_id: str
    status: str
    message: str
    created_at: datetime


class ResellerRegistrationRecord(BaseModel):
    id: str
    company_name: str
    email: EmailStr
    phone: Optional[str]
    invite_code: Optional[str]
    wholesale_slug: Optional[str]
    locale: Optional[str]
    keycloak_user_id: str
    status: str
    created_at: datetime

