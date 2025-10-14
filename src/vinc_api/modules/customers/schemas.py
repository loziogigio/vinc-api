from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

try:  # Prefer pydantic v2
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover - fallback when pydantic missing
    class BaseModel:  # type: ignore
        pass

    def Field(*args, **kwargs):  # type: ignore
        return kwargs.get("default")


class CustomerCreate(BaseModel):
    supplier_id: UUID
    erp_customer_id: str = Field(..., min_length=1)
    name: Optional[str] = None
    is_active: Optional[bool] = True

    # Contact information
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    # BMS Integration Fields - HIGH Priority
    customer_code: Optional[str] = None
    public_customer_code: Optional[str] = None
    business_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    fiscal_code: Optional[str] = Field(None, max_length=16)
    vat_number: Optional[str] = Field(None, max_length=11)
    registration_date: Optional[datetime] = None
    credit_limit: Optional[Decimal] = None

    # BMS Integration Fields - MEDIUM Priority
    customer_category: Optional[str] = None
    activity_category: Optional[str] = None
    gender: Optional[str] = Field(None, pattern="^[MFO]$")
    business_start_date: Optional[datetime] = None
    financial_status: Optional[str] = None
    cash_payment: Optional[bool] = None
    auto_packaging: Optional[bool] = None
    customer_group: Optional[str] = None


class CustomerUpdate(BaseModel):
    erp_customer_id: Optional[str] = Field(default=None, min_length=1)
    name: Optional[str] = None
    is_active: Optional[bool] = None

    # Contact information
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    # BMS Integration Fields - HIGH Priority
    customer_code: Optional[str] = None
    public_customer_code: Optional[str] = None
    business_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    fiscal_code: Optional[str] = Field(None, max_length=16)
    vat_number: Optional[str] = Field(None, max_length=11)
    registration_date: Optional[datetime] = None
    credit_limit: Optional[Decimal] = None

    # BMS Integration Fields - MEDIUM Priority
    customer_category: Optional[str] = None
    activity_category: Optional[str] = None
    gender: Optional[str] = Field(None, pattern="^[MFO]$")
    business_start_date: Optional[datetime] = None
    financial_status: Optional[str] = None
    cash_payment: Optional[bool] = None
    auto_packaging: Optional[bool] = None
    customer_group: Optional[str] = None


class CustomerResponse(BaseModel):
    id: UUID
    supplier_id: UUID
    erp_customer_id: str
    name: Optional[str]
    is_active: bool

    # Contact information
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None

    # BMS Integration Fields - HIGH Priority
    customer_code: Optional[str] = None
    public_customer_code: Optional[str] = None
    business_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    fiscal_code: Optional[str] = None
    vat_number: Optional[str] = None
    registration_date: Optional[datetime] = None
    credit_limit: Optional[Decimal] = None

    # BMS Integration Fields - MEDIUM Priority
    customer_category: Optional[str] = None
    activity_category: Optional[str] = None
    gender: Optional[str] = None
    business_start_date: Optional[datetime] = None
    financial_status: Optional[str] = None
    cash_payment: Optional[bool] = None
    auto_packaging: Optional[bool] = None
    customer_group: Optional[str] = None

    class Config:
        from_attributes = True


class CustomerDetailResponse(CustomerResponse):
    addresses: List["CustomerAddressResponse"]


class CustomerAddressCreate(BaseModel):
    erp_address_id: str = Field(..., min_length=1)
    label: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    pricelist_code: Optional[str] = None
    channel_code: Optional[str] = None
    type: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = True

    # BMS Integration Fields - HIGH Priority
    address_code: Optional[str] = None
    public_address_code: Optional[str] = None
    province: Optional[str] = Field(None, max_length=2)
    municipality: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    pricelist_type: Optional[str] = None
    payment_terms_code: Optional[str] = None
    is_billing_address: Optional[bool] = None
    is_shipping_address: Optional[bool] = None

    # BMS Integration Fields - MEDIUM Priority
    street_name: Optional[str] = None
    street_number: Optional[str] = None
    internal_number: Optional[str] = None
    region: Optional[str] = None
    zone_code: Optional[str] = None
    mobile_phone: Optional[str] = None
    fax: Optional[str] = None
    website: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    promo_pricelist_code: Optional[str] = None
    shipping_terms: Optional[str] = None
    transport_type: Optional[str] = None
    language_code: Optional[str] = Field(None, max_length=10)
    currency_code: Optional[str] = Field(None, max_length=10)
    carrier_code: Optional[str] = None
    is_payment_address: Optional[bool] = None
    is_delivery_address: Optional[bool] = None
    registration_date: Optional[datetime] = None
    iban: Optional[str] = Field(None, max_length=34)
    bic_swift: Optional[str] = Field(None, max_length=11)
    discount_1: Optional[Decimal] = None
    discount_2: Optional[Decimal] = None
    agent_code: Optional[str] = None
    sales_point_code: Optional[str] = None
    vat_code: Optional[str] = None
    credit_limit: Optional[Decimal] = None


class CustomerAddressUpdate(BaseModel):
    label: Optional[str] = None
    street: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    pricelist_code: Optional[str] = None
    channel_code: Optional[str] = None
    type: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None

    # BMS Integration Fields - HIGH Priority
    address_code: Optional[str] = None
    public_address_code: Optional[str] = None
    province: Optional[str] = Field(None, max_length=2)
    municipality: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    pricelist_type: Optional[str] = None
    payment_terms_code: Optional[str] = None
    is_billing_address: Optional[bool] = None
    is_shipping_address: Optional[bool] = None

    # BMS Integration Fields - MEDIUM Priority
    street_name: Optional[str] = None
    street_number: Optional[str] = None
    internal_number: Optional[str] = None
    region: Optional[str] = None
    zone_code: Optional[str] = None
    mobile_phone: Optional[str] = None
    fax: Optional[str] = None
    website: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    promo_pricelist_code: Optional[str] = None
    shipping_terms: Optional[str] = None
    transport_type: Optional[str] = None
    language_code: Optional[str] = Field(None, max_length=10)
    currency_code: Optional[str] = Field(None, max_length=10)
    carrier_code: Optional[str] = None
    is_payment_address: Optional[bool] = None
    is_delivery_address: Optional[bool] = None
    registration_date: Optional[datetime] = None
    iban: Optional[str] = Field(None, max_length=34)
    bic_swift: Optional[str] = Field(None, max_length=11)
    discount_1: Optional[Decimal] = None
    discount_2: Optional[Decimal] = None
    agent_code: Optional[str] = None
    sales_point_code: Optional[str] = None
    vat_code: Optional[str] = None
    credit_limit: Optional[Decimal] = None


class CustomerAddressResponse(BaseModel):
    id: UUID
    customer_id: UUID
    erp_customer_id: str
    erp_address_id: str
    label: Optional[str]
    street: Optional[str]
    city: Optional[str]
    zip: Optional[str]
    country: Optional[str]
    pricelist_code: Optional[str]
    channel_code: Optional[str]
    type: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: bool

    # BMS Integration Fields - HIGH Priority
    address_code: Optional[str] = None
    public_address_code: Optional[str] = None
    province: Optional[str] = None
    municipality: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    pricelist_type: Optional[str] = None
    payment_terms_code: Optional[str] = None
    is_billing_address: Optional[bool] = None
    is_shipping_address: Optional[bool] = None

    # BMS Integration Fields - MEDIUM Priority
    street_name: Optional[str] = None
    street_number: Optional[str] = None
    internal_number: Optional[str] = None
    region: Optional[str] = None
    zone_code: Optional[str] = None
    mobile_phone: Optional[str] = None
    fax: Optional[str] = None
    website: Optional[str] = None
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    promo_pricelist_code: Optional[str] = None
    shipping_terms: Optional[str] = None
    transport_type: Optional[str] = None
    language_code: Optional[str] = None
    currency_code: Optional[str] = None
    carrier_code: Optional[str] = None
    is_payment_address: Optional[bool] = None
    is_delivery_address: Optional[bool] = None
    registration_date: Optional[datetime] = None
    iban: Optional[str] = None
    bic_swift: Optional[str] = None
    discount_1: Optional[Decimal] = None
    discount_2: Optional[Decimal] = None
    agent_code: Optional[str] = None
    sales_point_code: Optional[str] = None
    vat_code: Optional[str] = None
    credit_limit: Optional[Decimal] = None

    class Config:
        from_attributes = True


CustomerDetailResponse.update_forward_refs()
