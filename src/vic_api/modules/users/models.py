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
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from ...core.db_base import Base

ROLE_VALUES = ("reseller", "agent", "viewer", "wholesale_admin", "super_admin")
STATUS_VALUES = ("invited", "active", "disabled")
USER_LINK_ROLE_VALUES = ("buyer", "viewer")


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

    customers: Mapped[List["Customer"]] = relationship(
        back_populates="supplier",
        cascade="all, delete-orphan",
    )
    addresses: Mapped[List["CustomerAddress"]] = relationship(
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

    supplier: Mapped[Supplier] = relationship(back_populates="customers")
    addresses: Mapped[List["CustomerAddress"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
        primaryjoin=lambda: Customer.erp_customer_id == foreign(CustomerAddress.erp_customer_id),
    )
    user_links: Mapped[List["UserCustomerLink"]] = relationship(
        back_populates="customer",
        cascade="all, delete-orphan",
    )


class CustomerAddress(Base):
    __tablename__ = "customer_address"
    __table_args__ = (
        UniqueConstraint("erp_customer_id", "erp_address_id"),
        Index("idx_customer_address_supplier", "supplier_id"),
    )

    id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    erp_address_id: Mapped[str] = mapped_column(String, nullable=False)
    erp_customer_id: Mapped[str] = mapped_column(String, nullable=False)
    supplier_id: Mapped[UUIDType] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("supplier.id", ondelete="CASCADE"),
        nullable=False,
    )
    label: Mapped[str | None] = mapped_column(String, nullable=True)
    street: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    zip: Mapped[str | None] = mapped_column(String, nullable=True)
    country: Mapped[str | None] = mapped_column(String, nullable=True)
    pricelist_code: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_code: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    supplier: Mapped[Supplier] = relationship(back_populates="addresses")
    customer: Mapped[Customer | None] = relationship(
        back_populates="addresses",
        primaryjoin=lambda: Customer.erp_customer_id == foreign(CustomerAddress.erp_customer_id),
        viewonly=True,
    )
    user_links: Mapped[List["UserAddressLink"]] = relationship(
        back_populates="customer_address",
        cascade="all, delete-orphan",
    )


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint(
            "role in ('reseller','agent','viewer','wholesale_admin','super_admin')",
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

    customer_links: Mapped[List["UserCustomerLink"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    address_links: Mapped[List["UserAddressLink"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserCustomerLink(Base):
    __tablename__ = "user_customer_link"
    __table_args__ = (
        CheckConstraint(
            "role in ('buyer','viewer')",
            name="role_valid",
        ),
        Index("idx_user_customer_user", "user_id"),
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

    user: Mapped[User] = relationship(back_populates="customer_links")
    customer: Mapped[Customer] = relationship(back_populates="user_links")


class UserAddressLink(Base):
    __tablename__ = "user_address_link"
    __table_args__ = (
        CheckConstraint(
            "role in ('buyer','viewer')",
            name="role_valid",
        ),
        Index("idx_user_address_user", "user_id"),
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

    user: Mapped[User] = relationship(back_populates="address_links")
    customer_address: Mapped[CustomerAddress] = relationship(back_populates="user_links")
