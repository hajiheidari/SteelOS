"""Exact exclusive sales tax with organization defaults and historical rate snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0004_sales_tax"
down_revision = "0003_sales_drafts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "organizations",
        sa.Column("sales_tax_rate_percent", sa.Numeric(9, 6), nullable=False, server_default="10"),
    )
    op.add_column(
        "organizations",
        sa.Column("tax_policy_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint(
        "ck_org_sales_tax_rate", "organizations", "sales_tax_rate_percent BETWEEN 0 AND 100"
    )
    op.create_check_constraint(
        "ck_org_tax_policy_version", "organizations", "tax_policy_version > 0"
    )
    op.add_column("sales_drafts", sa.Column("amount_rounding", sa.String(20), nullable=True))
    op.create_check_constraint(
        "ck_sales_draft_amount_rounding", "sales_drafts", "amount_rounding = 'half_up_2'"
    )
    # Existing drafts remain unconfigured: do not invent historical tax or change revisions.
    op.add_column("sales_drafts", sa.Column("tax_rate_percent", sa.Numeric(9, 6), nullable=True))
    op.create_check_constraint(
        "ck_sales_draft_tax_rate", "sales_drafts", "tax_rate_percent BETWEEN 0 AND 100"
    )


def downgrade():
    op.drop_constraint("ck_sales_draft_amount_rounding", "sales_drafts", type_="check")
    op.drop_column("sales_drafts", "amount_rounding")
    op.drop_constraint("ck_sales_draft_tax_rate", "sales_drafts", type_="check")
    op.drop_column("sales_drafts", "tax_rate_percent")
    op.drop_constraint("ck_org_tax_policy_version", "organizations", type_="check")
    op.drop_constraint("ck_org_sales_tax_rate", "organizations", type_="check")
    op.drop_column("organizations", "tax_policy_version")
    op.drop_column("organizations", "sales_tax_rate_percent")
