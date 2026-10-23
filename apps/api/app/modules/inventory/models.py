from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.db import Base
from app.models import Tenant
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column


class StockLot(Tenant, Base):
    __tablename__ = "inventory_lots"
    code: Mapped[str] = mapped_column(String(80))
    product_id: Mapped[UUID] = mapped_column()
    owner_kind: Mapped[str] = mapped_column(String(20))
    owner_party_id: Mapped[UUID | None] = mapped_column()
    unit: Mapped[str] = mapped_column(String(20))
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
        CheckConstraint(
            "(owner_kind = 'company' AND owner_party_id IS NULL) OR (owner_kind = 'party' AND owner_party_id IS NOT NULL)"
        ),
        CheckConstraint("unit IN ('kg','tonne','piece','m','m2')"),
        ForeignKeyConstraint(
            ["organization_id", "product_id"], ["products.organization_id", "products.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "owner_party_id"], ["parties.organization_id", "parties.id"]
        ),
    )


class StockReservation(Tenant, Base):
    __tablename__ = "inventory_reservations"
    lot_id: Mapped[UUID] = mapped_column()
    warehouse_id: Mapped[UUID] = mapped_column()
    location_id: Mapped[UUID] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 3))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reference: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "lot_id", "warehouse_id", "location_id", "id"),
        CheckConstraint("quantity > 0"),
        ForeignKeyConstraint(
            ["organization_id", "lot_id"], ["inventory_lots.organization_id", "inventory_lots.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id", "location_id"],
            ["locations.organization_id", "locations.warehouse_id", "locations.id"],
        ),
    )


class StockDraft(Tenant, Base):
    __tablename__ = "inventory_drafts"
    lot_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 3))
    from_warehouse_id: Mapped[UUID | None] = mapped_column()
    from_location_id: Mapped[UUID | None] = mapped_column()
    to_warehouse_id: Mapped[UUID | None] = mapped_column()
    to_location_id: Mapped[UUID | None] = mapped_column()
    reservation_id: Mapped[UUID | None] = mapped_column()
    reverses_id: Mapped[UUID | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    posted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "lot_id", "id"),
        CheckConstraint(
            "kind IN ('receipt','dispatch','transfer','block','unblock','reserve','release','fulfill','reversal')"
        ),
        CheckConstraint("status IN ('draft','posted','rejected')"),
        CheckConstraint("quantity > 0"),
        CheckConstraint(
            "(status = 'posted' AND posted_by IS NOT NULL AND posted_at IS NOT NULL) OR (status <> 'posted' AND posted_by IS NULL AND posted_at IS NULL)"
        ),
        CheckConstraint("(from_location_id IS NULL) = (from_warehouse_id IS NULL)"),
        CheckConstraint("(to_location_id IS NULL) = (to_warehouse_id IS NULL)"),
        CheckConstraint("(kind = 'reversal') = (reverses_id IS NOT NULL)"),
        CheckConstraint("(kind = 'reserve') = (expires_at IS NOT NULL)"),
        ForeignKeyConstraint(
            ["organization_id", "lot_id"], ["inventory_lots.organization_id", "inventory_lots.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "lot_id", "reverses_id"],
            ["inventory_drafts.organization_id", "inventory_drafts.lot_id", "inventory_drafts.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "reservation_id"],
            ["inventory_reservations.organization_id", "inventory_reservations.id"],
        ),
        *(
            ForeignKeyConstraint(
                ["organization_id", f"{side}_warehouse_id", f"{side}_location_id"],
                ["locations.organization_id", "locations.warehouse_id", "locations.id"],
            )
            for side in ("from", "to")
        ),
        Index(
            "uq_inventory_posted_reversal",
            "organization_id",
            "reverses_id",
            unique=True,
            postgresql_where=text("status = 'posted'"),
        ),
        Index(
            "uq_inventory_reservation_origin",
            "organization_id",
            "reservation_id",
            unique=True,
            postgresql_where=text("kind = 'reserve' AND status = 'posted'"),
        ),
    )


class StockEntry(Tenant, Base):
    __tablename__ = "inventory_entries"
    draft_id: Mapped[UUID] = mapped_column()
    lot_id: Mapped[UUID] = mapped_column()
    warehouse_id: Mapped[UUID] = mapped_column()
    location_id: Mapped[UUID] = mapped_column()
    reservation_id: Mapped[UUID | None] = mapped_column()
    on_hand_delta: Mapped[Decimal] = mapped_column(Numeric(20, 3), default=Decimal("0"))
    blocked_delta: Mapped[Decimal] = mapped_column(Numeric(20, 3), default=Decimal("0"))
    reserved_delta: Mapped[Decimal] = mapped_column(Numeric(20, 3), default=Decimal("0"))
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "draft_id",
            "warehouse_id",
            "location_id",
            name="uq_inventory_entry_position",
        ),
        CheckConstraint("on_hand_delta <> 0 OR blocked_delta <> 0 OR reserved_delta <> 0"),
        CheckConstraint("reserved_delta = 0 OR reservation_id IS NOT NULL"),
        ForeignKeyConstraint(
            ["organization_id", "lot_id", "draft_id"],
            ["inventory_drafts.organization_id", "inventory_drafts.lot_id", "inventory_drafts.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "warehouse_id", "location_id"],
            ["locations.organization_id", "locations.warehouse_id", "locations.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "lot_id", "warehouse_id", "location_id", "reservation_id"],
            [
                "inventory_reservations.organization_id",
                "inventory_reservations.lot_id",
                "inventory_reservations.warehouse_id",
                "inventory_reservations.location_id",
                "inventory_reservations.id",
            ],
        ),
        Index("ix_inventory_position", "organization_id", "lot_id", "warehouse_id", "location_id"),
    )
