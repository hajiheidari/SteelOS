from uuid import UUID

from app.db import Base
from app.models import Tenant
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column


class AgentSource(Tenant, Base):
    __tablename__ = "agent_sources"
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    attribution: Mapped[str] = mapped_column(String(1000))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("kind IN ('internal_note','public_excerpt')", name="ck_agent_source_kind"),
    )


class AgentRun(Tenant, Base):
    __tablename__ = "agent_runs"
    kind: Mapped[str] = mapped_column(String(30))
    brief: Mapped[str] = mapped_column(Text)
    output: Mapped[dict] = mapped_column(JSON)
    model_name: Mapped[str] = mapped_column(String(80))
    policy_version: Mapped[str] = mapped_column(String(40))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "kind IN ('research','education','marketing','sales')", name="ck_agent_run_kind"
        ),
    )


class AgentEvidence(Tenant, Base):
    __tablename__ = "agent_evidence"
    run_id: Mapped[UUID] = mapped_column()
    source_id: Mapped[UUID] = mapped_column()
    alias: Mapped[str] = mapped_column(String(2))
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (
        UniqueConstraint("organization_id", "run_id", "source_id"),
        UniqueConstraint("organization_id", "run_id", "alias"),
        ForeignKeyConstraint(
            ["organization_id", "run_id"], ["agent_runs.organization_id", "agent_runs.id"]
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_id"], ["agent_sources.organization_id", "agent_sources.id"]
        ),
    )


class AgentReview(Tenant, Base):
    __tablename__ = "agent_reviews"
    run_id: Mapped[UUID] = mapped_column()
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (
        UniqueConstraint("organization_id", "run_id"),
        CheckConstraint("decision IN ('accepted','rejected')", name="ck_agent_review_decision"),
        ForeignKeyConstraint(
            ["organization_id", "run_id"], ["agent_runs.organization_id", "agent_runs.id"]
        ),
    )
