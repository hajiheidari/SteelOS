"""Local invoice intake and immutable transcription revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0006_invoice_intake"
down_revision = "0005_sales_review"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invoice_intakes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(40), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("engine", sa.String(100), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("extraction", sa.JSON(), nullable=False),
        sa.Column("corrected_text", sa.Text(), nullable=False),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "source_sha256"),
        sa.CheckConstraint("version > 0", name="ck_intake_version"),
        sa.CheckConstraint("page_count BETWEEN 1 AND 3", name="ck_intake_pages"),
        sa.CheckConstraint("status IN ('draft','reviewed')", name="ck_intake_status"),
    )
    op.create_index("ix_invoice_intakes_organization_id", "invoice_intakes", ["organization_id"])
    op.create_table(
        "invoice_intake_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("intake_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id", "intake_id"],
            ["invoice_intakes.organization_id", "invoice_intakes.id"],
        ),
        sa.UniqueConstraint("organization_id", "intake_id", "version"),
        sa.CheckConstraint("version > 0", name="ck_intake_revision_version"),
    )
    op.create_index(
        "ix_invoice_intake_revisions_organization_id",
        "invoice_intake_revisions",
        ["organization_id"],
    )
    op.execute("""
    CREATE FUNCTION guard_invoice_intake() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Invoice intake history retained' USING ERRCODE='23514'; END IF;
      IF NEW.id<>OLD.id OR NEW.organization_id<>OLD.organization_id OR NEW.source_sha256<>OLD.source_sha256
        OR NEW.media_type<>OLD.media_type OR NEW.page_count<>OLD.page_count OR NEW.engine<>OLD.engine
        OR NEW.raw_text<>OLD.raw_text OR NEW.extraction::jsonb<>OLD.extraction::jsonb
        OR NEW.created_by<>OLD.created_by OR NEW.created_at<>OLD.created_at OR NEW.version<>OLD.version+1 THEN
        RAISE EXCEPTION 'Immutable invoice source or invalid version' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER invoice_intake_guard BEFORE UPDATE OR DELETE ON invoice_intakes
      FOR EACH ROW EXECUTE FUNCTION guard_invoice_intake();
    CREATE FUNCTION guard_invoice_intake_revision() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Immutable invoice revision' USING ERRCODE='23514'; END IF;
      IF NOT EXISTS(SELECT 1 FROM invoice_intakes WHERE id=NEW.intake_id AND organization_id=NEW.organization_id AND version=NEW.version) THEN
        RAISE EXCEPTION 'Invalid invoice revision version' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER invoice_intake_revision_guard BEFORE INSERT OR UPDATE OR DELETE ON invoice_intake_revisions
      FOR EACH ROW EXECUTE FUNCTION guard_invoice_intake_revision();
    """)


def downgrade():
    op.drop_table("invoice_intake_revisions")
    op.drop_table("invoice_intakes")
    op.execute(
        "DROP FUNCTION guard_invoice_intake_revision(); DROP FUNCTION guard_invoice_intake()"
    )
