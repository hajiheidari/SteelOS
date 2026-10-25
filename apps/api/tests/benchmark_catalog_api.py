"""Opt-in real loopback HTTP catalog experiment; never run against business/test data."""

import argparse
import asyncio
import json
import math
import secrets
import socket
import statistics
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn
from app import models as m
from app.db import engine
from app.main import app
from app.security import digest, hasher
from benchmark_catalog_search import seed_catalog
from benchmark_support import exclusive_database
from sqlalchemy import delete, event, func, insert, select, text


@contextmanager
def loopback_server():
    # Pre-bind an ephemeral loopback port; never expose a public listener or race a port probe.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                log_level="warning",
                access_log=False,
                timeout_graceful_shutdown=5,
            )
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() >= deadline:
                    raise RuntimeError("Loopback API failed to start")
                time.sleep(0.01)
            yield f"http://127.0.0.1:{listener.getsockname()[1]}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            if thread.is_alive():
                raise RuntimeError("Loopback API did not stop; inspect benchmark database")


@contextmanager
def bounded_connections(database):
    def timeout(connection, record, proxy):
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '15s'")
        connection.commit()

    event.listen(database, "checkout", timeout)
    try:
        yield
    finally:
        event.remove(database, "checkout", timeout)
        # Do not leave benchmark timeout settings on idle pooled connections.
        database.dispose()


def cases():
    return [
        ("name", {"q": "ورق"}, lambda i: True),
        ("literal_identifier", {"q": "ref%_\\123"}, lambda i: str(i).startswith("123")),
        ("missing_identifier", {"q": "UNSEEN-ALIAS"}, lambda i: False),
        (
            "identifier_range",
            {
                "q": "REF",
                "attributes": json.dumps(
                    {
                        "thickness": {
                            "min": {"value": "0.2", "unit": "cm"},
                            "max": {"value": "3", "unit": "mm"},
                        }
                    }
                ),
            },
            lambda i: 2 <= i % 10 + 1 <= 3,
        ),
    ]


def verify_page(body, organization, expected):
    assert body["total"] == len(expected)
    assert body["offset"] == 0 and body["limit"] == 5
    assert [item["id"] for item in body["items"]] == [str(row["id"]) for row in expected[:5]]
    for item, row in zip(body["items"], expected[:5], strict=True):
        assert item["organization_id"] == str(organization)
        assert item["sku"] == row["sku"] and item["attributes"] == row["attributes"]
        category_name = "ورق مصنوعی " + row["attributes"]["thickness"]["unit"]
        assert item["display_names"]["category_id"] == category_name
        assert item["category_rules"]["thickness"]["required"] is True


async def measure(base_url, credentials, datasets, concurrency, repeats):
    async with httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=30) as client:
        tokens = []
        for credential in credentials:
            result = await client.post("/api/v1/auth/login", json=credential)
            assert result.status_code == 200, result.status_code
            tokens.append({"Authorization": "Bearer " + result.json()["access_token"]})
        specifications = cases()
        expected = {
            (org_index, name): sorted(
                [row for row in rows if row["active"] and predicate(int(row["sku"][4:]))],
                key=lambda row: row["sku"],
            )
            for org_index, rows in enumerate(datasets)
            for name, _, predicate in specifications
        }

        async def request(client, org_index, specification):
            name, params, _ = specification
            started = time.perf_counter()
            result = await client.get(
                "/api/v1/products",
                headers=tokens[org_index],
                params={
                    **params,
                    "active": "true",
                    "sort": "sku",
                    "direction": "asc",
                    "limit": 5,
                },
            )
            elapsed = (time.perf_counter() - started) * 1000
            assert result.status_code == 200, result.status_code
            assert result.headers["cache-control"] == "no-store"
            verify_page(
                result.json(), credentials[org_index]["organization_id"], expected[org_index, name]
            )
            return name, elapsed

        # All case/tenant combinations warm up outside timing; no latency pass/fail threshold.
        for org_index in range(2):
            for specification in specifications:
                await request(client, org_index, specification)
        workloads = []
        for clients in concurrency:

            async def worker(index):
                samples = []
                async with httpx.AsyncClient(
                    base_url=base_url, trust_env=False, timeout=30
                ) as local:
                    for iteration in range(repeats):
                        for offset in range(len(specifications)):
                            spec = specifications[(index + offset) % len(specifications)]
                            samples.append(await request(local, (index + iteration) % 2, spec))
                return samples

            started = time.perf_counter()
            # Await every worker before cleanup even when one fails validation or times out.
            results = await asyncio.gather(
                *(worker(index) for index in range(clients)), return_exceptions=True
            )
            duration = time.perf_counter() - started
            for result in results:
                if isinstance(result, BaseException):
                    raise result
            samples = [sample for result in results for sample in result]
            workloads.append(
                {
                    "concurrency": clients,
                    "requests": len(samples),
                    "duration_seconds": round(duration, 3),
                    "requests_per_second": round(len(samples) / duration, 3),
                    "cases": [
                        {
                            "name": name,
                            "samples": len(times),
                            "median_ms": round(statistics.median(times), 3),
                            "p95_ms": round(sorted(times)[math.ceil(len(times) * 0.95) - 1], 3),
                        }
                        for name, _, _ in specifications
                        for times in [[elapsed for case, elapsed in samples if case == name]]
                    ],
                }
            )
        return workloads


def cleanup(connection, organizations, users, emails):
    """Delete only this experiment's generated scope and verify every seeded/auth table."""
    with connection.begin():
        connection.execute(text("SET LOCAL statement_timeout = '15s'"))
        for model in (
            m.AuthSession,
            m.AuditEvent,
            m.Membership,
            m.ProductIdentifier,
            m.Product,
            m.Reference,
        ):
            connection.execute(delete(model).where(model.organization_id.in_(organizations)))
        connection.execute(delete(m.Organization).where(m.Organization.id.in_(organizations)))
        connection.execute(delete(m.User).where(m.User.id.in_(users)))
        connection.execute(
            delete(m.LoginAttempt).where(
                m.LoginAttempt.key.in_([digest(email) for email in emails])
            )
        )
    cleaned_up = all(
        connection.scalar(select(func.count()).select_from(model).where(column.in_(ids))) == 0
        for model, column, ids in [
            (m.Organization, m.Organization.id, organizations),
            (m.Product, m.Product.organization_id, organizations),
            (m.ProductIdentifier, m.ProductIdentifier.organization_id, organizations),
            (m.User, m.User.id, users),
            (m.AuthSession, m.AuthSession.organization_id, organizations),
            (m.AuditEvent, m.AuditEvent.organization_id, organizations),
            (m.Membership, m.Membership.organization_id, organizations),
            (m.Reference, m.Reference.organization_id, organizations),
            (m.LoginAttempt, m.LoginAttempt.key, [digest(email) for email in emails]),
        ]
    )
    return cleaned_up


def benchmark(rows_per_org=5000, repeats=10, concurrency=(1, 4)):
    if not 100 <= rows_per_org <= 50000 or not 3 <= repeats <= 20:
        raise SystemExit("rows-per-org must be100..50000; repeats must be3..20")
    if (
        not concurrency
        or len(set(concurrency)) != len(concurrency)
        or any(c not in (1, 2, 4) for c in concurrency)
    ):
        raise SystemExit("Unique concurrency values must be1,2,4")
    database = engine()
    report = {
        "scope": "Synthetic real loopback HTTP, one API worker; not a production SLO",
        "recorded_at": datetime.now(UTC).isoformat(),
        "rows_per_organization": rows_per_org,
        "organizations": 2,
        "identifiers_per_product": 2,
        "repeats_per_client": repeats,
    }
    users, credentials, organizations = [], [], []
    with exclusive_database(database) as connection, bounded_connections(database):
        try:
            with connection.begin():
                connection.execute(text("SET LOCAL statement_timeout = '15s'"))
                report["postgres_version"] = connection.scalar(text("SHOW server_version"))
                organizations, _ = seed_catalog(connection, rows_per_org, True)
                password = secrets.token_urlsafe(24)
                password_hash = hasher.hash(password)
                for organization in organizations:
                    user_id = uuid.uuid4()
                    email = f"synthetic-{user_id}@benchmark.test"
                    users.append(user_id)
                    connection.execute(
                        insert(m.User),
                        {
                            "id": user_id,
                            "email": email,
                            "password_hash": password_hash,
                            "active": True,
                        },
                    )
                    connection.execute(
                        insert(m.Membership),
                        {
                            "id": uuid.uuid4(),
                            "user_id": user_id,
                            "organization_id": organization,
                            "role": "viewer",
                        },
                    )
                    credentials.append(
                        {"email": email, "password": password, "organization_id": str(organization)}
                    )
                datasets = [
                    connection.execute(
                        select(m.Product.__table__).where(m.Product.organization_id == organization)
                    )
                    .mappings()
                    .all()
                    for organization in organizations
                ]
                connection.execute(text("ANALYZE products"))
                connection.execute(text("ANALYZE product_identifiers"))
            # Commit is necessary: concurrent HTTP requests use independent DB transactions.
            with loopback_server() as base_url:
                report["workloads"] = asyncio.run(
                    measure(base_url, credentials, datasets, concurrency, repeats)
                )
        finally:
            connection.rollback()
            report["cleaned_up"] = cleanup(
                connection, organizations, users, [c["email"] for c in credentials]
            )
            assert report["cleaned_up"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows-per-org", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = benchmark(args.rows_per_org, args.repeats, args.concurrency)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, ensure_ascii=False))
