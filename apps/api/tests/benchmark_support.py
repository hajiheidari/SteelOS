"""Opt-in experiments share one fail-closed database guard; no application dependency."""

from contextlib import contextmanager

from app.models import Organization
from sqlalchemy import func, select, text


@contextmanager
def exclusive_database(database):
    if not database.url.database or not database.url.database.endswith("_benchmark"):
        raise SystemExit("Use an isolated, migrated DATABASE_URL ending in _benchmark")
    with database.connect() as connection:
        locked = connection.scalar(
            text("SELECT pg_try_advisory_lock(hashtext('steelos_catalog_benchmark'))")
        )
        connection.commit()
        if not locked:
            raise SystemExit("Another catalog benchmark holds this database")
        try:
            if connection.scalar(select(func.count()).select_from(Organization)):
                raise SystemExit("Benchmark database must contain no organizations")
            connection.rollback()
            yield connection
        finally:
            connection.rollback()
            connection.execute(
                text("SELECT pg_advisory_unlock(hashtext('steelos_catalog_benchmark'))")
            )
            connection.commit()
