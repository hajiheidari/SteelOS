"""Synthetic-only PostgreSQL custom-archive recovery drill; never an operational backup."""

import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app import models as m
from app.db import SCHEMA_REVISION, Base, database, engine
from app.main import app
from app.modules.invoices import ocr
from conftest import create
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def checked_target(url, container):
    if not url.database or not re.fullmatch(r"[a-zA-Z0-9_]+_test", url.database):
        raise ValueError("A dedicated disposable *_test database is required")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}", container):
        raise ValueError("Explicit local PostgreSQL test container required")
    return "steelos_restore_" + uuid4().hex + "_test"


def docker(container, arguments, **streams):
    # The test container must belong to this local daemon, never a saved remote context.
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
        }
    }
    return subprocess.run(
        ["docker", "--host=unix:///var/run/docker.sock", "exec", "-i", container, *arguments],
        env=env,
        check=True,
        timeout=60,
        stderr=subprocess.PIPE,
        **streams,
    )


def rows(db):
    with db.connect() as connection:
        return {
            table.name: connection.execute(select(table).order_by(*table.primary_key)).all()
            for table in Base.metadata.sorted_tables
        }


def schema(db):
    with db.connect() as connection:
        return {
            "constraints": connection.execute(
                text("""
                SELECT c.conname, c.contype, c.convalidated, c.condeferrable, c.condeferred,
                       CASE WHEN c.contype='c' THEN c.conkey::text
                            ELSE pg_get_constraintdef(c.oid) END
                FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace
                WHERE n.nspname='public' ORDER BY 1,2
            """)
            ).all(),
            "triggers": connection.execute(
                text("""
                SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid)
                FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2
            """)
            ).all(),
            "columns": connection.execute(
                text("""
                SELECT table_name, column_name, ordinal_position, data_type,
                       is_nullable, character_maximum_length, numeric_precision, numeric_scale
                FROM information_schema.columns WHERE table_schema='public'
                ORDER BY table_name,ordinal_position
            """)
            ).all(),
            "indexes": connection.execute(
                text("""
                SELECT tablename,indexname,indexdef FROM pg_indexes
                WHERE schemaname='public' ORDER BY 1,2
            """)
            ).all(),
        }


@pytest.mark.parametrize("name", ["steelos", "postgres", "customer_prod", 'bad"_test'])
def test_restore_drill_rejects_non_disposable_names(name):
    from sqlalchemy.engine import make_url

    with pytest.raises(ValueError):
        checked_target(make_url("postgresql+psycopg://localhost/" + name), "test-postgres")


@pytest.mark.skipif(
    not os.environ.get("POSTGRES_TEST_CONTAINER"), reason="Explicit local test container required"
)
def test_synthetic_postgres_custom_archive_restore(world, catalog, monkeypatch, tmp_path):
    client, tokens, orgs, _ = world
    source = engine()
    container = os.environ["POSTGRES_TEST_CONTAINER"]
    target = checked_target(source.url, container)
    # Refuse a container pointing at another cluster before any archive/create/restore action.
    with source.connect() as connection:
        cluster = str(connection.scalar(text("SELECT system_identifier FROM pg_control_system()")))
    actual = docker(
        container,
        [
            "psql",
            "-U",
            source.url.username,
            "-d",
            "postgres",
            "-Atc",
            "SELECT system_identifier FROM pg_control_system()",
        ],
        stdout=subprocess.PIPE,
    )
    assert actual.stdout.decode().strip() == cluster, "Test container does not match DATABASE_URL"
    party = create(
        client,
        tokens[0],
        "parties",
        {"name": "بازیابی مصنوعی", "kind": "legal_entity", "roles": ["customer", "supplier"]},
    )
    follow = create(
        client,
        tokens[0],
        "crm-follow-ups",
        {
            "name": "پیگیری بازیابی",
            "party_id": party["id"],
            "due_at": "2099-01-01T12:00:00+03:30",
            "notes": "متن فارسی",
        },
    )
    warehouse = create(
        client,
        tokens[0],
        "warehouses",
        {"code": "RESTORE", "name": "انبار مصنوعی", "city": "تهران", "address": "مصنوعی"},
    )
    location = create(
        client,
        tokens[0],
        "locations",
        {"warehouse_id": warehouse["id"], "code": "HALL", "name": "سالن", "kind": "hall"},
    )
    lot = create(
        client,
        tokens[0],
        "inventory/lots",
        {
            "code": "RESTORE",
            "product_id": catalog[2]["id"],
            "owner_kind": "party",
            "owner_party_id": party["id"],
            "unit": "kg",
        },
    )
    movement = create(
        client,
        tokens[0],
        "inventory/drafts",
        {
            "lot_id": lot["id"],
            "kind": "receipt",
            "quantity": "1234.567",
            "to_location_id": location["id"],
            "reference": "Synthetic restore drill",
        },
    )
    assert (
        client.post(
            "/api/v1/inventory/drafts/" + movement["id"] + "/post",
            headers={**tokens[0], "Idempotency-Key": "restore-post"},
        ).status_code
        == 200
    )
    price_source = create(
        client,
        tokens[0],
        "price-sources",
        {
            "code": "RESTORE",
            "name": "مصنوعی",
            "kind": "manual",
            "provenance": "Synthetic only",
            "approved": True,
        },
    )
    now = datetime.now(UTC)
    price = create(
        client,
        tokens[0],
        "price-observations",
        {
            "source_id": price_source["id"],
            "product_id": catalog[2]["id"],
            "amount": "123456.123456",
            "currency": "IRR",
            "unit": "kg",
            "observed_at": (now - timedelta(minutes=1)).isoformat(),
            "valid_until": (now + timedelta(hours=1)).isoformat(),
            "delivery_location": "تهران",
            "delivery_terms": "مصنوعی",
            "tax_included": False,
            "provenance": "Synthetic only",
        },
    )
    assert (
        client.post(
            "/api/v1/price-observations/" + price["id"] + "/decision",
            headers=tokens[0],
            json={"status": "approved"},
        ).status_code
        == 200
    )
    sale = create(
        client,
        tokens[0],
        "sales-drafts",
        {
            "code": "RESTORE",
            "customer_id": party["id"],
            "currency": "IRR",
            "lines": [{"price_id": price["id"], "quantity": "2.123"}],
        },
    )
    monkeypatch.setattr(
        ocr, "extract", lambda *args: ("Seller: Synthetic\nGrand total: 271.59", 1, "test-fixture")
    )
    invoice = client.post(
        "/api/v1/invoice-intakes/extract",
        headers={**tokens[0], "Content-Type": "image/png", "Idempotency-Key": "restore-invoice"},
        content=b"synthetic-restore",
    )
    assert invoice.status_code == 201
    expected_rows, expected_schema = rows(source), schema(source)
    assert (
        expected_rows["inventory_entries"]
        and expected_rows["sales_draft_revisions"]
        and expected_rows["invoice_intake_revisions"]
    )
    target_url = source.url.set(database=target)
    admin = create_engine(source.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    restored = None
    created = False
    archive = tmp_path / "synthetic.dump"
    try:
        # Exclusive create: never DROP/clean an existing database, even on name collision.
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{target}"'))
        created = True
        with archive.open("xb") as output:
            os.chmod(archive, 0o600)
            docker(
                container,
                [
                    "pg_dump",
                    "-U",
                    source.url.username,
                    "-d",
                    source.url.database,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                ],
                stdout=output,
            )
        with archive.open("rb") as input_file:
            docker(
                container,
                [
                    "pg_restore",
                    "-U",
                    source.url.username,
                    "-d",
                    target,
                    "--exit-on-error",
                    "--single-transaction",
                    "--no-owner",
                    "--no-acl",
                ],
                stdin=input_file,
                stdout=subprocess.PIPE,
            )
        restored = create_engine(target_url)
        assert set(inspect(restored).get_table_names()) == set(inspect(source).get_table_names())
        assert rows(restored) == expected_rows
        actual_schema = schema(restored)
        differences = {
            key: (
                set(actual_schema[key]) - set(expected_schema[key]),
                set(expected_schema[key]) - set(actual_schema[key]),
            )
            for key in expected_schema
            if actual_schema[key] != expected_schema[key]
        }
        assert not differences, differences
        with restored.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                == SCHEMA_REVISION
            )
        # Restored append-only triggers and tenant FKs must enforce, not merely be present.
        with Session(restored) as db:
            for statement in (
                "UPDATE inventory_entries SET on_hand_delta=on_hand_delta+1",
                "DELETE FROM sales_draft_revisions",
                "DELETE FROM invoice_intake_revisions",
            ):
                with pytest.raises(IntegrityError):
                    db.execute(text(statement))
                db.rollback()
            for statement in (
                "UPDATE organizations SET sales_tax_rate_percent=101",
                "UPDATE crm_follow_ups SET status='approved'",
                "UPDATE inventory_lots SET owner_kind='unknown'",
                "UPDATE price_observations SET amount=-1",
            ):
                with pytest.raises(IntegrityError):
                    db.execute(text(statement))
                db.rollback()
            db.add(
                m.FollowUp(
                    organization_id=UUID(orgs[1]),
                    party_id=UUID(party["id"]),
                    name="Foreign",
                    kind="call",
                    due_at=now,
                    status="open",
                    notes="",
                )
            )
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        def restored_database():
            with Session(restored) as db:
                yield db

        app.dependency_overrides[database] = restored_database
        assert (
            client.get("/api/v1/crm-follow-ups/" + follow["id"], headers=tokens[0]).json()["notes"]
            == "متن فارسی"
        )
        assert (
            client.get("/api/v1/crm-follow-ups/" + follow["id"], headers=tokens[1]).status_code
            == 404
        )
        assert (
            client.get("/api/v1/sales-drafts/" + sale["id"], headers=tokens[0]).json()[
                "estimated_total"
            ]
            == sale["estimated_total"]
        )
        assert rows(source) == expected_rows  # Restore/verification never touched the source.
    finally:
        app.dependency_overrides.pop(database, None)
        if restored:
            restored.dispose()
        try:
            if created:
                with admin.connect() as connection:
                    connection.execute(text(f'DROP DATABASE "{target}"'))
        finally:
            admin.dispose()
            archive.unlink(missing_ok=True)
