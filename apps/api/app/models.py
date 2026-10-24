"""Core persistence with modular M2 inventory registration and tenant-aware FKs."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Identity:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Organization(Identity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(200))


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(Identity, Base):
    __tablename__ = "memberships"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id"),
        CheckConstraint("role IN ('admin','editor','viewer')"),
    )


class AuthSession(Identity, Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
    )


class Tenant(Identity):
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)


class Reference(Tenant, Base):
    __tablename__ = "catalog_references"
    kind: Mapped[str] = mapped_column(String(30))
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    attribute_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "kind", "code"),
        CheckConstraint("kind IN ('category','manufacturer','grade','standard')"),
    )


class Product(Tenant, Base):
    __tablename__ = "products"
    sku: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    category_id: Mapped[uuid.UUID] = mapped_column()
    manufacturer_id: Mapped[uuid.UUID | None] = mapped_column()
    grade_id: Mapped[uuid.UUID | None] = mapped_column()
    standard_id: Mapped[uuid.UUID | None] = mapped_column()
    unit: Mapped[str] = mapped_column(String(20))
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    specification_hash: Mapped[str] = mapped_column(String(64))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "sku"),
        UniqueConstraint("organization_id", "specification_hash"),
        *(
            ForeignKeyConstraint(
                ["organization_id", f"{field}_id"],
                ["catalog_references.organization_id", "catalog_references.id"],
            )
            for field in ("category", "manufacturer", "grade", "standard")
        ),
        CheckConstraint("unit IN ('kg','tonne','piece','m','m2')"),
    )


class ProductIdentifier(Tenant, Base):
    __tablename__ = "product_identifiers"
    product_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(30))
    value: Mapped[str] = mapped_column(String(100))
    __table_args__ = (
        UniqueConstraint("organization_id", "kind", "value"),
        ForeignKeyConstraint(
            ["organization_id", "product_id"], ["products.organization_id", "products.id"]
        ),
    )


class Party(Tenant, Base):
    __tablename__ = "parties"
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    registration_id: Mapped[str | None] = mapped_column(String(30))
    roles: Mapped[list] = mapped_column(JSON)
    contacts: Mapped[list] = mapped_column(JSON, default=list)
    addresses: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "registration_id"),
        CheckConstraint("kind IN ('individual','legal_entity')"),
    )


class Warehouse(Tenant, Base):
    __tablename__ = "warehouses"
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(100))
    address: Mapped[str] = mapped_column(String(1000))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
    )


class WarehouseAccess(Tenant, Base):
    __tablename__ = "warehouse_access"
    warehouse_id: Mapped[uuid.UUID] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column()
    __table_args__ = (
        UniqueConstraint("organization_id", "warehouse_id", "user_id"),
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id"], ["warehouses.organization_id", "warehouses.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"], ["memberships.organization_id", "memberships.user_id"]
        ),
    )


class Location(Tenant, Base):
    __tablename__ = "locations"
    warehouse_id: Mapped[uuid.UUID] = mapped_column()
    parent_id: Mapped[uuid.UUID | None] = mapped_column()
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    __table_args__ = (
        UniqueConstraint("organization_id", "warehouse_id", "id"),
        UniqueConstraint("organization_id", "warehouse_id", "code"),
        CheckConstraint("parent_id IS NULL OR parent_id <> id"),
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id"], ["warehouses.organization_id", "warehouses.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id", "parent_id"],
            ["locations.organization_id", "locations.warehouse_id", "locations.id"],
        ),
    )


class PriceSource(Tenant, Base):
    __tablename__ = "price_sources"
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    provenance: Mapped[str] = mapped_column(String(2000))
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
        CheckConstraint("kind IN ('manual','mock')"),
    )


class PriceObservation(Tenant, Base):
    __tablename__ = "price_observations"
    product_id: Mapped[uuid.UUID] = mapped_column()
    source_id: Mapped[uuid.UUID] = mapped_column()
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    currency: Mapped[str] = mapped_column(String(3))
    unit: Mapped[str] = mapped_column(String(20))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivery_location: Mapped[str] = mapped_column(String(500))
    delivery_terms: Mapped[str] = mapped_column(String(1000))
    tax_included: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    provenance: Mapped[str] = mapped_column(String(2000))
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_price_observations_org_id"),
        CheckConstraint("amount > 0"),
        CheckConstraint("valid_until > observed_at"),
        CheckConstraint("status IN ('pending','approved','rejected')"),
        CheckConstraint("unit IN ('kg','tonne','piece','m','m2')"),
        ForeignKeyConstraint(
            ["organization_id", "product_id"], ["products.organization_id", "products.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_id"], ["price_sources.organization_id", "price_sources.id"]
        ),
    )


class AuditEvent(Tenant, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    resource: Mapped[str] = mapped_column(String(80))
    resource_id: Mapped[uuid.UUID] = mapped_column()


class IdempotencyRecord(Tenant, Base):
    __tablename__ = "idempotency_records"
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    key: Mapped[str] = mapped_column(String(100))
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint("organization_id", "actor_id", "key"),)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))


# Register modular inventory tables with the same SQLAlchemy metadata/migration graph.
from app.modules.inventory.models import (  # noqa: E402,F401
    StockDraft,
    StockEntry,
    StockLot,
    StockReservation,
)
from app.modules.sales.models import SalesDraft, SalesDraftLine, SalesDraftRevision  # noqa: E402,F401
