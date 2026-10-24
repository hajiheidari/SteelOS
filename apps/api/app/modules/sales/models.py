from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.db import Base
from app.models import Tenant
from sqlalchemy import (
    JSON,
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


class SalesDraft(Tenant, Base):
    __tablename__ = "sales_drafts"
    code: Mapped[str] = mapped_column(String(80))
    customer_id: Mapped[UUID] = mapped_column()
    currency: Mapped[str] = mapped_column(String(3))
    amount_rounding: Mapped[str | None] = mapped_column(String(20))
    tax_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    note: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "code"),
        CheckConstraint("status IN ('draft','cancelled')"),
        CheckConstraint("version > 0"),
        CheckConstraint("amount_rounding = 'half_up_2'", name="ck_sales_draft_amount_rounding"),
        CheckConstraint("tax_rate_percent BETWEEN 0 AND 100", name="ck_sales_draft_tax_rate"),
        CheckConstraint("currency IN ('IRR','IRT','USD','EUR')"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"], ["parties.organization_id", "parties.id"]
        ),
    )


class SalesDraftLine(Tenant, Base):
    __tablename__ = "sales_draft_lines"
    draft_id: Mapped[UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[UUID] = mapped_column()
    price_id: Mapped[UUID] = mapped_column()
    source_id: Mapped[UUID] = mapped_column()
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 3))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(24, 6))
    unit: Mapped[str] = mapped_column(String(20))
    price_valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("organization_id", "draft_id", "position"),
        UniqueConstraint("organization_id", "draft_id", "price_id"),
        CheckConstraint("quantity > 0 AND unit_price > 0"),
        CheckConstraint("position BETWEEN 1 AND 100"),
        CheckConstraint("unit IN ('kg','tonne','piece','m','m2')"),
        ForeignKeyConstraint(
            ["organization_id", "draft_id"], ["sales_drafts.organization_id", "sales_drafts.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "product_id"], ["products.organization_id", "products.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "price_id"],
            ["price_observations.organization_id", "price_observations.id"],
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_id"], ["price_sources.organization_id", "price_sources.id"]
        ),
    )


class SalesDraftRevision(Tenant, Base):
    __tablename__ = "sales_draft_revisions"
    draft_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("organization_id", "draft_id", "version"),
        CheckConstraint("version > 0"),
        ForeignKeyConstraint(
            ["organization_id", "draft_id"], ["sales_drafts.organization_id", "sales_drafts.id"]
        ),
    )


class SalesDraftReview(Tenant, Base):
    __tablename__ = "sales_draft_reviews"
    draft_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(String(2000))
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("organization_id", "draft_id", "version"),
        CheckConstraint("decision IN ('accepted','rejected')"),
        CheckConstraint("decision <> 'rejected' OR length(trim(note)) > 0"),
        ForeignKeyConstraint(
            ["organization_id", "draft_id", "version"],
            [
                "sales_draft_revisions.organization_id",
                "sales_draft_revisions.draft_id",
                "sales_draft_revisions.version",
            ],
        ),
    )
