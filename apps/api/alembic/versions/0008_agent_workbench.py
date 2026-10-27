"""Internal human-controlled agent drafts and immutable evidence; no financial tools."""

import sqlalchemy as sa
from alembic import op

revision = "0008_agent_workbench"
down_revision = "0007_crm_follow_ups"
branch_labels = None
depends_on = None


def tenant():
    return [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "agent_sources",
        *tenant(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_url", sa.String(2000)),
        sa.Column("attribution", sa.String(1000), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("organization_id", "id"),
        sa.CheckConstraint(
            "kind IN ('internal_note','public_excerpt')", name="ck_agent_source_kind"
        ),
    )
    op.create_table(
        "agent_runs",
        *tenant(),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("brief", sa.Text(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(40), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("organization_id", "id"),
        sa.CheckConstraint(
            "kind IN ('research','education','marketing','sales')", name="ck_agent_run_kind"
        ),
    )
    op.create_table(
        "agent_evidence",
        *tenant(),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(2), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.UniqueConstraint("organization_id", "run_id", "source_id"),
        sa.UniqueConstraint("organization_id", "run_id", "alias"),
        sa.ForeignKeyConstraint(
            ["organization_id", "run_id"], ["agent_runs.organization_id", "agent_runs.id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_id"], ["agent_sources.organization_id", "agent_sources.id"]
        ),
    )
    op.create_table(
        "agent_reviews",
        *tenant(),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("organization_id", "run_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "run_id"], ["agent_runs.organization_id", "agent_runs.id"]
        ),
        sa.CheckConstraint("decision IN ('accepted','rejected')", name="ck_agent_review_decision"),
    )
    for table in ("agent_sources", "agent_runs", "agent_evidence", "agent_reviews"):
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    op.execute("""CREATE FUNCTION steelos_agent_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Agent evidence/history is immutable' USING ERRCODE='23514'; END $$""")
    for table in ("agent_runs", "agent_evidence", "agent_reviews"):
        op.execute(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION steelos_agent_immutable()"
        )
    op.execute("""CREATE FUNCTION steelos_agent_source_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Source history cannot be deleted' USING ERRCODE='23514'; END IF;
            IF (to_jsonb(NEW)-'active') IS DISTINCT FROM (to_jsonb(OLD)-'active') OR (NOT OLD.active AND NEW.active) THEN
                RAISE EXCEPTION 'Only source revocation is allowed' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute(
        "CREATE TRIGGER agent_source_guard BEFORE UPDATE OR DELETE ON agent_sources FOR EACH ROW EXECUTE FUNCTION steelos_agent_source_guard()"
    )


def downgrade():
    for table in ("agent_reviews", "agent_evidence", "agent_runs", "agent_sources"):
        op.drop_table(table)
    op.execute("DROP FUNCTION steelos_agent_source_guard()")
    op.execute("DROP FUNCTION steelos_agent_immutable()")
