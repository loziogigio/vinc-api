from __future__ import annotations

from datetime import datetime
from typing import List
from uuid import UUID as UUIDType, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from ...core.db_base import Base

ROLE_VALUES = (
    "reseller",
    "agent",
    "viewer",
    "wholesale_admin",
    "supplier_admin",
    "wholesaler_helpdesk",
    "super_admin",
)
STATUS_VALUES = ("invited", "active", "disabled")
USER_LINK_ROLE_VALUES = ("buyer", "viewer")
USER_SUPPLIER_LINK_ROLE_VALUES = ("admin", "helpdesk", "viewer")


class Supplier(Base):
    __tablename__ = "supplier"

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    legal_name: Mapped[str | None] = mapped_column(String, nullable=True)
    legal_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    legal_email: Mapped[str | None] = mapped_column(String, nullable=True)
    legal_number: Mapped[str | None] = mapped_column(String, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'active'"))

    customers: Mapped[List["Customer"]] = relationship(
        back_populates="supplier",
        cascade="all, delete-orphan",
    )
    user_links: Mapped[List["UserSupplierLink"]] = relationship(
        back_populates="supplier",
        cascade="all, delete-orphan",
    )


class Customer(Base):
    __tablename__ = "customer"

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    erp_customer_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    supplier_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("supplier.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # Contact information
    contact_email: Mapped[str | None] = mapped_column(String, nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String, nullable=True)

    # BMS/ERP Integration Fields - HIGH Priority
    customer_code: Mapped[str | None] = mapped_column(String, nullable=True)
    public_customer_code: Mapped[str | None] = mapped_column(String, nullable=True)
    business_name: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    fiscal_code: Mapped[str | None] = mapped_column(String, nullable=True)
    vat_number: Mapped[str | None] = mapped_column(String, nullable=True)
    registration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    credit_limit: Mapped[float | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)

    # BMS/ERP Integration Fields - MEDIUM Priority
    customer_category: Mapped[str | None] = mapped_column(String, nullable=True)
    activity_category: Mapped[str | None] = mapped_column(String, nullable=True)
    gender: Mapped[str | None] = mapped_column(String, nullable=True)
    business_start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    financial_status: Mapped[str | None] = mapped_column(String, nullable=True)
    cash_payment: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    auto_packaging: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    customer_group: Mapped[str | None] = mapped_column(String, nullable=True)

    supplier: Mapped[Supplier] = relationship(back_populates="customers")
    addresses: Mapped[List["CustomerAddress"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )
    user_links: Mapped[List["UserCustomerLink"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class CustomerAddress(Base):
    __tablename__ = "customer_address"
    __table_args__ = (
        UniqueConstraint("erp_customer_id", "erp_address_id"),
    )

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    erp_address_id: Mapped[str] = mapped_column(String, nullable=False)
    erp_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    customer_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Basic fields
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    street: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    zip: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    pricelist_code: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_code: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    type: Mapped[str | None] = mapped_column(String, nullable=True)
    is_default: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # BMS/ERP Integration Fields - HIGH Priority
    address_code: Mapped[str | None] = mapped_column(String, nullable=True)
    public_address_code: Mapped[str | None] = mapped_column(String, nullable=True)
    province: Mapped[str | None] = mapped_column(String, nullable=True)
    municipality: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    pricelist_type: Mapped[str | None] = mapped_column(String, nullable=True)
    payment_terms_code: Mapped[str | None] = mapped_column(String, nullable=True)
    is_billing_address: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_shipping_address: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # BMS/ERP Integration Fields - MEDIUM Priority
    street_name: Mapped[str | None] = mapped_column(String, nullable=True)
    street_number: Mapped[str | None] = mapped_column(String, nullable=True)
    internal_number: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    zone_code: Mapped[str | None] = mapped_column(String, nullable=True)
    mobile_phone: Mapped[str | None] = mapped_column(String, nullable=True)
    fax: Mapped[str | None] = mapped_column(String, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(precision=10, scale=8), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(precision=11, scale=8), nullable=True)
    promo_pricelist_code: Mapped[str | None] = mapped_column(String, nullable=True)
    shipping_terms: Mapped[str | None] = mapped_column(String, nullable=True)
    transport_type: Mapped[str | None] = mapped_column(String, nullable=True)
    language_code: Mapped[str | None] = mapped_column(String, nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String, nullable=True)
    carrier_code: Mapped[str | None] = mapped_column(String, nullable=True)
    is_payment_address: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_delivery_address: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    registration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    iban: Mapped[str | None] = mapped_column(String, nullable=True)
    bic_swift: Mapped[str | None] = mapped_column(String, nullable=True)
    discount_1: Mapped[float | None] = mapped_column(Numeric(precision=5, scale=3), nullable=True)
    discount_2: Mapped[float | None] = mapped_column(Numeric(precision=5, scale=3), nullable=True)
    agent_code: Mapped[str | None] = mapped_column(String, nullable=True)
    sales_point_code: Mapped[str | None] = mapped_column(String, nullable=True)
    vat_code: Mapped[str | None] = mapped_column(String, nullable=True)
    credit_limit: Mapped[float | None] = mapped_column(Numeric(precision=12, scale=2), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="addresses")
    user_links: Mapped[List["UserAddressLink"]] = relationship(
        back_populates="customer_address",
        cascade="all, delete-orphan",
    )


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "role in ('reseller','agent','viewer','wholesale_admin','supplier_admin','wholesaler_helpdesk','super_admin')",
            name="role_valid",
        ),
        CheckConstraint(
            "status in ('invited','active','disabled')",
            name="status_valid",
        ),
    )

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    role: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="invited",
        server_default=text("'invited'"),
    )
    auth_provider: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="keycloak",
        server_default=text("'keycloak'"),
    )
    kc_user_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    supplier_id: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("supplier.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    supplier: Mapped[Supplier | None] = relationship()
    supplier_links: Mapped[List["UserSupplierLink"]] = relationship(
        back_populates="user",
        foreign_keys="[UserSupplierLink.user_id]",
        cascade="all, delete-orphan",
    )
    customer_links: Mapped[List["UserCustomerLink"]] = relationship(
        back_populates="user",
        foreign_keys="[UserCustomerLink.user_id]",
        cascade="all, delete-orphan",
    )
    address_links: Mapped[List["UserAddressLink"]] = relationship(
        back_populates="user",
        foreign_keys="[UserAddressLink.user_id]",
        cascade="all, delete-orphan",
    )


class UserCustomerLink(Base):
    __tablename__ = "user_customer_link"
    __table_args__ = (
        CheckConstraint(
            "role in ('buyer','viewer')",
            name="user_customer_link_role_valid",
        ),
        CheckConstraint(
            "status in ('pending','active','suspended','revoked')",
            name="user_customer_link_status_valid",
        ),
        Index("idx_user_customer_user", "user_id"),
        Index("idx_user_customer_link_status", "status"),
        Index("idx_user_customer_link_is_active", "is_active"),
        Index("idx_user_customer_link_created_at", "created_at"),
    )

    user_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    customer_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customer.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="buyer",
        server_default=text("'buyer'"),
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="customer_links", foreign_keys=[user_id])
    customer: Mapped[Customer] = relationship(back_populates="user_links")


class UserAddressLink(Base):
    __tablename__ = "user_address_link"
    __table_args__ = (
        CheckConstraint(
            "role in ('buyer','viewer')",
            name="user_address_link_role_valid",
        ),
        CheckConstraint(
            "status in ('pending','active','suspended','revoked')",
            name="user_address_link_status_valid",
        ),
        Index("idx_user_address_user", "user_id"),
        Index("idx_user_address_link_status", "status"),
        Index("idx_user_address_link_is_active", "is_active"),
        Index("idx_user_address_link_created_at", "created_at"),
    )

    user_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    customer_address_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customer_address.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="buyer",
        server_default=text("'buyer'"),
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="address_links", foreign_keys=[user_id])
    customer_address: Mapped[CustomerAddress] = relationship(back_populates="user_links")


class UserSupplierLink(Base):
    __tablename__ = "user_supplier_link"
    __table_args__ = (
        CheckConstraint(
            "role in ('admin','helpdesk','viewer')",
            name="role_valid",
        ),
        CheckConstraint(
            "status in ('pending','active','suspended','revoked')",
            name="status_valid",
        ),
        Index("idx_user_supplier_user", "user_id"),
        Index("idx_user_supplier_supplier", "supplier_id"),
        Index("idx_user_supplier_link_status", "status"),
        Index("idx_user_supplier_link_is_active", "is_active"),
        Index("idx_user_supplier_link_created_at", "created_at"),
    )

    user_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        primary_key=True,
    )
    supplier_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("supplier.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="viewer",
        server_default=text("'viewer'"),
    )
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="active",
        server_default=text("'active'"),
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    approved_by: Mapped[UUIDType | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="supplier_links", foreign_keys=[user_id])
    supplier: Mapped[Supplier] = relationship(back_populates="user_links")
