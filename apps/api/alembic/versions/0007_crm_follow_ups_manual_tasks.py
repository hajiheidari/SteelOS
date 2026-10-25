"""Manual CRM follow-ups, separate from trading and external communication."""

import sqlalchemy as sa
from alembic import op

revision = "0007_crm_follow_ups"
down_revision = "0006_invoice_intake"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_follow_ups",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("party_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.String(1000), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(
            ["organization_id", "party_id"], ["parties.organization_id", "parties.id"]
        ),
        sa.CheckConstraint(
            "kind IN ('call','meeting','document','other')", name="ck_follow_up_kind"
        ),
        sa.CheckConstraint(
            "status IN ('open','completed','cancelled')", name="ck_follow_up_status"
        ),
    )
    op.create_index("ix_crm_follow_ups_organization_id", "crm_follow_ups", ["organization_id"])
    op.create_index("ix_crm_follow_ups_due_at", "crm_follow_ups", ["due_at"])


def downgrade():
    op.drop_table("crm_follow_ups")
