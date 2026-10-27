"""Untrusted document transcriptions; no financial or stock references."""

import uuid
from datetime import datetime

from app.db import Base
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column


class InvoiceIntake(Base):
    __tablename__ = "invoice_intakes"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    source_sha256: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(40))
    page_count: Mapped[int] = mapped_column(Integer)
    engine: Mapped[str] = mapped_column(String(100))
    raw_text: Mapped[str] = mapped_column(Text)
    extraction: Mapped[dict] = mapped_column(JSON)
    corrected_text: Mapped[str] = mapped_column(Text)
    fields: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "source_sha256"),
        CheckConstraint("version > 0", name="ck_intake_version"),
        CheckConstraint("page_count BETWEEN 1 AND 3", name="ck_intake_pages"),
        CheckConstraint("status IN ('draft','reviewed')", name="ck_intake_status"),
    )


class InvoiceIntakeRevision(Base):
    __tablename__ = "invoice_intake_revisions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    intake_id: Mapped[uuid.UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "intake_id"],
            ["invoice_intakes.organization_id", "invoice_intakes.id"],
        ),
        UniqueConstraint("organization_id", "intake_id", "version"),
        CheckConstraint("version > 0", name="ck_intake_revision_version"),
    )
