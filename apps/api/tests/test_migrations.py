import os
import subprocess
import sys
from pathlib import Path

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
