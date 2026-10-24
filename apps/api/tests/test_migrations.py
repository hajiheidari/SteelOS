import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

from app.db import Base
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


def test_postgres_upgrade_downgrade_roundtrip():
    url = make_url(os.environ["DATABASE_URL"])
    if not url.database.endswith("_test"):
        raise RuntimeError("Disposable test database required")
    migration_db = url.database + "_migration_test"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        # Controlled name derived only from test database configuration.
        connection.execute(text(f'DROP DATABASE IF EXISTS "{migration_db}"'))
        connection.execute(text(f'CREATE DATABASE "{migration_db}"'))
    env = {
        **os.environ,
        "DATABASE_URL": url.set(database=migration_db).render_as_string(hide_password=False),
    }
    directory = Path(__file__).resolve().parents[1]
    db = create_engine(env["DATABASE_URL"])
    try:
        # Upgrade a populated M1 installation before the clean roundtrip.
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0001_m1"],
            cwd=directory,
            env=env,
            check=True,
            capture_output=True,
        )
        with db.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organizations (id, name) VALUES "
                    "('11111111-1111-1111-1111-111111111111', 'Existing M1 organization')"
                )
            )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "0003_sales_drafts"],
            cwd=directory,
            env=env,
            check=True,
            capture_output=True,
        )
        org_id = UUID("11111111-1111-1111-1111-111111111111")
        actor_id = UUID("22222222-2222-2222-2222-222222222222")
        party_id = UUID("33333333-3333-3333-3333-333333333333")
        draft_id = UUID("44444444-4444-4444-4444-444444444444")
        legacy = {"currency": "IRR", "estimated_total": "0.000000001"}
        with db.begin() as connection:
            connection.execute(
                Base.metadata.tables["users"]
                .insert()
                .values(
                    id=actor_id,
                    email="migration@example.test",
                    password_hash="synthetic-test-only",
                )
            )
            connection.execute(
                Base.metadata.tables["parties"]
                .insert()
                .values(
                    id=party_id,
                    organization_id=org_id,
                    name="Legacy customer",
                    kind="individual",
                    roles=["customer"],
                )
            )
            connection.execute(
                Base.metadata.tables["sales_drafts"]
                .insert()
                .values(
                    id=draft_id,
                    organization_id=org_id,
                    code="LEGACY",
                    customer_id=party_id,
                    currency="IRR",
                    created_by=actor_id,
                    updated_by=actor_id,
                )
            )
            connection.execute(
                Base.metadata.tables["sales_draft_revisions"]
                .insert()
                .values(
                    organization_id=org_id,
                    draft_id=draft_id,
                    version=1,
                    actor_id=actor_id,
                    snapshot=legacy,
                )
            )
        first_head_checked = False
        for revision in ("head", "base", "head"):
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "downgrade" if revision == "base" else "upgrade",
                    revision,
                ],
                cwd=directory,
                env=env,
                check=True,
                capture_output=True,
            )
            if revision == "head" and not first_head_checked:
                # Only the first head contains the M1 fixture; base deliberately drops it.
                with db.connect() as connection:
                    assert (
                        connection.scalar(
                            text(
                                "SELECT name FROM organizations WHERE id = "
                                "'11111111-1111-1111-1111-111111111111'"
                            )
                        )
                        == "Existing M1 organization"
                    )
                with db.connect() as connection:
                    assert (
                        connection.scalar(text("SELECT sales_tax_rate_percent FROM organizations"))
                        == 10
                    )
                    assert (
                        connection.scalar(text("SELECT tax_rate_percent FROM sales_drafts")) is None
                    )
                    assert (
                        connection.scalar(text("SELECT snapshot FROM sales_draft_revisions"))
                        == legacy
                    )
                first_head_checked = True
            tables = set(inspect(db).get_table_names()) - {"alembic_version"}
            assert tables == (set() if revision == "base" else set(Base.metadata.tables))
        subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=directory,
            env=env,
            check=True,
            capture_output=True,
        )
    finally:
        db.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE "{migration_db}"'))
        admin.dispose()
