"""Destructive benchmark entry points must fail closed and clean up only their scope."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from app import models as m
from app.db import engine
from benchmark_catalog_api import benchmark, cleanup
from benchmark_support import exclusive_database
from conftest import create
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError


@pytest.mark.parametrize("name", ["steelos", "steelos_test", None])
def test_benchmark_refuses_other_database_before_connecting(name):
    database = MagicMock(url=SimpleNamespace(database=name))
    with pytest.raises(SystemExit, match="ending in _benchmark"):
        with exclusive_database(database):
            pytest.fail("Unsafe database guard yielded")
    database.connect.assert_not_called()


@pytest.mark.parametrize("locked,organizations", [(False, 0), (True, 1)])
def test_benchmark_refuses_busy_or_nonempty_database(locked, organizations):
    database = MagicMock(url=SimpleNamespace(database="isolated_benchmark"))
    connection = database.connect.return_value.__enter__.return_value
    connection.scalar.side_effect = [locked, organizations]
    with pytest.raises(SystemExit):
        with exclusive_database(database):
            pytest.fail("Busy/nonempty database guard yielded")
    assert connection.scalar.call_count == (2 if locked else 1)
    if locked:
        assert "pg_advisory_unlock" in str(connection.execute.call_args.args[0])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"rows_per_org": 99},
        {"repeats": 2},
        {"concurrency": [8]},
        {"concurrency": [1, 1]},
    ],
)
def test_http_benchmark_rejects_unbounded_work_before_database_access(monkeypatch, kwargs):
    import benchmark_catalog_api

    def unsafe_connect():
        pytest.fail("Invalid benchmark options reached database access")

    monkeypatch.setattr(benchmark_catalog_api, "engine", unsafe_connect)
    with pytest.raises(SystemExit):
        benchmark(**kwargs)


def test_http_benchmark_cleanup_refuses_unexpected_business_history(world, catalog):
    client, tokens, orgs, users = world
    _, _, product = catalog
    create(
        client,
        tokens[0],
        "product-identifiers",
        {
            "product_id": product["id"],
            "kind": "barcode",
            "value": "Synthetic-cleanup",
        },
    )
    # Real API creates add idempotency history, which the read-only benchmark never creates.
    # Cleanup must fail/roll back instead of erasing unexpected business history.
    with engine().connect() as connection:
        with pytest.raises(IntegrityError):
            cleanup(
                connection,
                [UUID(orgs[0])],
                [UUID(users[0]), UUID(users[2])],
                ["user0@example.test", "user2@example.test"],
            )
        assert connection.scalar(select(func.count()).select_from(m.Organization)) == 2
        assert connection.scalar(select(func.count()).select_from(m.User)) == 3
        assert connection.scalar(select(func.count()).select_from(m.Product)) == 1
        assert connection.scalar(select(func.count()).select_from(m.ProductIdentifier)) == 1
    for headers in tokens:
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_http_benchmark_cleans_committed_seed_after_workload_failure(world, catalog, monkeypatch):
    from contextlib import contextmanager

    import benchmark_catalog_api

    client, tokens, *_ = world

    @contextmanager
    def isolated_test_connection(database):
        # Only this test bypasses the suffix/empty guard to preserve pre-existing fixture tenants.
        # All real seed/cleanup transactions remain on the fixture's disposable *_test database.
        assert database.url.database.endswith("_test")
        with database.connect() as connection:
            yield connection

    @contextmanager
    def failed_transport():
        yield "http://unused.invalid"

    async def failure(*args, **kwargs):
        raise RuntimeError("synthetic HTTP failure")

    monkeypatch.setattr(benchmark_catalog_api, "exclusive_database", isolated_test_connection)
    monkeypatch.setattr(benchmark_catalog_api, "loopback_server", failed_transport)
    monkeypatch.setattr(benchmark_catalog_api, "measure", failure)
    with pytest.raises(RuntimeError, match="synthetic HTTP failure"):
        benchmark(rows_per_org=100, repeats=3, concurrency=[1])
    with engine().connect() as connection:
        assert connection.scalar(select(func.count()).select_from(m.Organization)) == 2
        assert connection.scalar(select(func.count()).select_from(m.User)) == 3
        assert connection.scalar(select(func.count()).select_from(m.Product)) == 1
        assert connection.scalar(select(func.count()).select_from(m.Reference)) == 1
        assert connection.scalar(select(func.count()).select_from(m.ProductIdentifier)) == 0
        assert connection.scalar(select(func.count()).select_from(m.AuthSession)) == 3
    for headers in tokens:
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
