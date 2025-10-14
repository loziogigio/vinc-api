from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.mongo import get_mongo_db
from ..users.models import Customer, CustomerAddress, Supplier

try:  # Prefer pydantic v2
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover - fallback when pydantic missing
    class BaseModel:  # type: ignore
        pass

    def Field(default: Any = None, **_: Any) -> Any:  # type: ignore
        return default


# -------------------- Membership Schema (Mongo) ----------------------------


class MembershipEntry(BaseModel):
    scope_type: str = Field(description="e.g. 'supplier' | 'agent' | 'global'")
    scope_id: Optional[str] = Field(default=None, description="UUID string or 'global'")
    role: str
    capabilities: List[str] = Field(default_factory=list)
    # Optional scoping fields
    reseller_scope: Optional[str] = None  # 'all' | 'list'
    reseller_account_ids: Optional[List[str]] = None
    address_scope: Optional[str] = None  # 'all' | 'list'
    address_ids: Optional[List[str]] = None
    # Optional limits/flags
    limits: Optional[Dict[str, Any]] = None
    flags: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class MembershipDoc(BaseModel):
    user_key: str  # prefer Keycloak sub; fallback to user UUID
    default_role: Optional[str] = None
    memberships: List[MembershipEntry] = Field(default_factory=list)


def _safe_uuid(value: Optional[str]) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None


class MembershipProcessingError(Exception):
    """Raised when membership documents cannot be resolved into scopes."""


@dataclass(slots=True)
class MembershipScope:
    supplier_id: Optional[str]
    allowed_customer_ids: List[str]
    allowed_address_ids: List[str]
    allowed_wholesalers: List[str]
    multi_tenant: bool


class PermissionsContext(BaseModel):
    active_wholesaler_id: Optional[str] = None
    allowed_reseller_account_ids: List[str] = Field(default_factory=list)
    allowed_address_ids: List[str] = Field(default_factory=list)
    capabilities: List[str] = Field(default_factory=list)


# -------------------- Defaults & Helpers ----------------------------------


_ROLE_DEFAULT_CAPS: dict[str, Set[str]] = {
    "super_admin": {
        "manage_suppliers",
        "manage_resellers",
        "manage_agents",
        "manage_configs",
        "place_orders",
        "view_orders",
        "view_data",
    },
    # Legacy + new names
    "wholesale_admin": {"manage_resellers", "manage_agents", "manage_configs", "view_orders", "view_data"},
    "wholesaler_helpdesk": {"support_read", "view_orders"},
    "supplier_admin": {"manage_resellers", "manage_agents", "manage_configs", "view_orders", "view_data"},
    "supplier_helpdesk": {"support_read", "view_orders"},
    "agent_admin": {"place_orders", "view_orders"},
    "agent": {"place_orders", "view_orders"},
    "reseller": {"place_orders", "view_orders"},
    "viewer": {"view_orders", "view_data"},
}


def _default_caps_for_role(role: Optional[str]) -> Set[str]:
    if not role:
        return set()
    role = role.lower()
    return set(_ROLE_DEFAULT_CAPS.get(role, set()))


def _load_customers_for_supplier(db: Session, supplier_id: UUID) -> List[Customer]:
    stmt = select(Customer).where(
        Customer.supplier_id == supplier_id,
        Customer.is_active.is_(True),
    )
    return db.execute(stmt).scalars().all()


def _load_addresses_for_supplier(db: Session, supplier_id: UUID) -> List[CustomerAddress]:
    stmt = (
        select(CustomerAddress)
        .join(Customer, Customer.id == CustomerAddress.customer_id)
        .where(
            Customer.supplier_id == supplier_id,
            CustomerAddress.is_active.is_(True),
        )
    )
    return db.execute(stmt).scalars().all()


# -------------------- Mongo Accessors -------------------------------------


async def _load_membership_doc(user_key: str) -> Optional[MembershipDoc]:
    db = get_mongo_db()
    if db is None:
        return None
    doc = await db["user_memberships"].find_one({"user_key": user_key})
    if not doc:
        return None
    try:
        return MembershipDoc.model_validate(doc)
    except Exception:
        # Best effort: coerce common shapes
        memberships = doc.get("memberships") or []
        return MembershipDoc(user_key=str(doc.get("user_key") or user_key), default_role=doc.get("default_role"), memberships=[MembershipEntry(**m) for m in memberships if isinstance(m, dict)])


async def load_membership_doc(user_key: str) -> Optional[MembershipDoc]:
    return await _load_membership_doc(user_key)


def _select_membership_for_scope(mdoc: MembershipDoc, active_wholesaler_id: Optional[str]) -> List[MembershipEntry]:
    entries: List[MembershipEntry] = []
    if not mdoc or not mdoc.memberships:
        return entries
    # Always include global memberships
    for m in mdoc.memberships:
        if m.scope_type == "global":
            entries.append(m)
    if active_wholesaler_id:
        for m in mdoc.memberships:
            if m.scope_type == "supplier" and (m.scope_id or "").lower() == str(active_wholesaler_id).lower():
                entries.append(m)
    return entries


# -------------------- Resolution API --------------------------------------


async def resolve_permissions(
    db: Session,
    *,
    user_key: str,
    active_wholesaler_id: Optional[str],
) -> PermissionsContext:
    """Resolve permissions and scoping for a request.

    - Load memberships from Mongo (if available)
    - Determine effective capabilities for the active wholesaler (and global)
    - Expand reseller/account/address scope when explicit ids are provided
    - Do not attempt heavy expansion (e.g., address_scope='all') yet to keep
      this lightweight; default to Postgres links or defaults.
    """
    mdoc = await _load_membership_doc(user_key)
    caps: Set[str] = set()
    allowed_resellers: Set[str] = set()
    allowed_addresses: Set[str] = set()

    customer_cache: dict[UUID, List[Customer]] = {}
    address_cache: dict[UUID, List[CustomerAddress]] = {}

    active_supplier_uuid = _safe_uuid(active_wholesaler_id)

    if mdoc:
        selected = _select_membership_for_scope(mdoc, active_wholesaler_id)
        # Aggregate capabilities and explicit scopes
        for entry in selected:
            caps.update(c.lower() for c in (entry.capabilities or []))
            supplier_uuid: Optional[UUID] = None
            if entry.scope_type == "supplier" and entry.scope_id:
                try:
                    supplier_uuid = UUID(entry.scope_id)
                except ValueError:
                    supplier_uuid = None

            reseller_scope = (entry.reseller_scope or "").lower()
            if reseller_scope == "list" and entry.reseller_account_ids:
                for rid in entry.reseller_account_ids:
                    if rid:
                        allowed_resellers.add(str(rid))
            elif (
                reseller_scope == "all"
                and supplier_uuid is not None
                and active_supplier_uuid is not None
                and supplier_uuid == active_supplier_uuid
            ):
                customers = customer_cache.get(supplier_uuid)
                if customers is None:
                    customers = _load_customers_for_supplier(db, supplier_uuid)
                    customer_cache[supplier_uuid] = customers
                for cust in customers:
                    allowed_resellers.add(str(cust.id))

            address_scope = (entry.address_scope or "").lower()
            if address_scope == "list" and entry.address_ids:
                for aid in entry.address_ids:
                    if aid:
                        allowed_addresses.add(str(aid))
            elif (
                address_scope == "all"
                and supplier_uuid is not None
                and active_supplier_uuid is not None
                and supplier_uuid == active_supplier_uuid
            ):
                addresses = address_cache.get(supplier_uuid)
                if addresses is None:
                    addresses = _load_addresses_for_supplier(db, supplier_uuid)
                    address_cache[supplier_uuid] = addresses
                for addr in addresses:
                    allowed_addresses.add(str(addr.id))
        # If no explicit capabilities provided for entries, fall back to role defaults
        if not caps:
            # Prefer the role from the most specific membership; fallback to default_role
            roles = [e.role for e in selected if e.role] or ([mdoc.default_role] if mdoc.default_role else [])
            for role in roles:
                caps.update(_default_caps_for_role(role))

    # If Mongo not present or doc empty, derive defaults from nothing here.
    # Callers may merge with JWT claims (allowed_*).

    # Sanity filter by active wholesaler when explicit reseller ids are given
    if allowed_resellers and active_supplier_uuid is not None:
        try:
            stmt = select(Customer).where(
                Customer.supplier_id == active_supplier_uuid,
                Customer.id.in_([UUID(rid) for rid in allowed_resellers]),
            )
            rows = db.execute(stmt).scalars().all()
            allowed_resellers = {str(row.id) for row in rows}
        except Exception:
            # If parsing fails, leave as-is
            pass

    # Expand addresses only for explicitly provided ids at this stage.
    # A later iteration can support address_scope='all' by querying Postgres.

    return PermissionsContext(
        active_wholesaler_id=str(active_wholesaler_id) if active_wholesaler_id else None,
        allowed_reseller_account_ids=sorted(allowed_resellers),
        allowed_address_ids=sorted(allowed_addresses),
        capabilities=sorted(caps),
    )


def list_suppliers_from_memberships(db: Session, mdoc: Optional[MembershipDoc]) -> List[Supplier]:
    if not mdoc:
        return []
    supplier_ids: List[UUID] = []
    for m in mdoc.memberships:
        if m.scope_type == "supplier" and m.scope_id:
            try:
                supplier_ids.append(UUID(m.scope_id))
            except Exception:
                continue
    if not supplier_ids:
        return []
    stmt = select(Supplier).where(Supplier.id.in_(supplier_ids))
    return db.execute(stmt).scalars().all()


async def persist_membership_doc(doc: MembershipDoc) -> MembershipDoc:
    db = get_mongo_db()
    if db is None:
        raise RuntimeError("Membership store unavailable")
    payload = doc.model_dump()
    await db["user_memberships"].update_one(
        {"user_key": doc.user_key},
        {"$set": payload},
        upsert=True,
    )
    return doc


def unique_supplier_scope_ids(doc: MembershipDoc) -> List[str]:
    seen: set[str] = set()
    results: List[str] = []
    for entry in doc.memberships:
        if entry.scope_type != "supplier" or not entry.scope_id:
            continue
        scope = entry.scope_id.lower()
        if scope in seen:
            continue
        seen.add(scope)
        results.append(entry.scope_id)
    return results


def derive_roles_from_memberships(doc: MembershipDoc) -> List[str]:
    roles: List[str] = []
    for entry in doc.memberships:
        if entry.role:
            roles.append(entry.role)
    if doc.default_role:
        roles.append(doc.default_role)
    return roles


def expand_scope_for_supplier(
    db: Session,
    *,
    doc: MembershipDoc,
    supplier_id: str,
) -> tuple[list[str], list[str]]:
    supplier_uuid = _safe_uuid(supplier_id)
    if supplier_uuid is None:
        return [], []

    allowed_resellers: Set[str] = set()
    allowed_addresses: Set[str] = set()

    customer_cache: Optional[List[Customer]] = None
    address_cache: Optional[List[CustomerAddress]] = None

    for entry in doc.memberships:
        entry_supplier_uuid = _safe_uuid(entry.scope_id) if entry.scope_type == "supplier" else None
        applies = entry.scope_type == "global" or entry_supplier_uuid == supplier_uuid
        if not applies:
            continue

        reseller_scope = (entry.reseller_scope or "").lower()
        if reseller_scope == "list" and entry.reseller_account_ids:
            for rid in entry.reseller_account_ids:
                if rid:
                    allowed_resellers.add(str(rid))
        elif reseller_scope == "all":
            if customer_cache is None:
                customer_cache = _load_customers_for_supplier(db, supplier_uuid)
            for cust in customer_cache:
                allowed_resellers.add(str(cust.id))

        address_scope = (entry.address_scope or "").lower()
        if address_scope == "list" and entry.address_ids:
            for aid in entry.address_ids:
                if aid:
                    allowed_addresses.add(str(aid))
        elif address_scope == "all":
            if address_cache is None:
                address_cache = _load_addresses_for_supplier(db, supplier_uuid)
            for addr in address_cache:
                allowed_addresses.add(str(addr.id))

    return sorted(allowed_resellers), sorted(allowed_addresses)


def process_membership_scope(db: Session, doc: MembershipDoc) -> MembershipScope:
    supplier_ids = unique_supplier_scope_ids(doc)
    if not supplier_ids:
        raise MembershipProcessingError("Membership must include at least one supplier scope")

    allowed_wholesalers = [scope for scope in supplier_ids if scope]

    if len(supplier_ids) == 1:
        supplier_id = supplier_ids[0]
        allowed_customers, allowed_addresses = expand_scope_for_supplier(
            db,
            doc=doc,
            supplier_id=supplier_id,
        )
        # Allow empty customer/address scopes so new suppliers without seeded data
        # can still persist memberships; downstream logic handles empty link lists.
        return MembershipScope(
            supplier_id=supplier_id,
            allowed_customer_ids=allowed_customers,
            allowed_address_ids=allowed_addresses,
            allowed_wholesalers=allowed_wholesalers,
            multi_tenant=False,
        )

    return MembershipScope(
        supplier_id=supplier_ids[0],
        allowed_customer_ids=[],
        allowed_address_ids=[],
        allowed_wholesalers=allowed_wholesalers,
        multi_tenant=True,
    )
