from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app import models as m
from app.db import engine
from app.modules.inventory import service
from conftest import create
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def inventory(world, catalog):
    client, tokens, orgs, users = world
    warehouses, locations = [], []
    for code in ("A", "B"):
        warehouse = create(
            client,
            tokens[0],
            "warehouses",
            {"code": code, "name": "انبار " + code, "city": "تهران", "address": "Test"},
        )
        location = create(
            client,
            tokens[0],
            "locations",
            {
                "warehouse_id": warehouse["id"],
                "code": "hall",
                "name": "سالن " + code,
                "kind": "hall",
            },
        )
        warehouses.append(warehouse)
        locations.append(location)
    party = create(
        client,
        tokens[0],
        "parties",
        {"name": "صاحب کالا", "kind": "legal_entity", "roles": ["customer"]},
    )
    lot_data = {
        "code": "LOT-A",
        "product_id": catalog[2]["id"],
        "owner_kind": "party",
        "owner_party_id": party["id"],
        "unit": "kg",
    }
    lot = create(client, tokens[0], "inventory/lots", lot_data)
    return client, tokens, orgs, users, warehouses, locations, party, lot, lot_data


def draft(env, kind, quantity="10", token=0, **fields):
    client, tokens, _, _, _, locations, _, lot, _ = env
    data = {
        "lot_id": lot["id"],
        "kind": kind,
        "quantity": quantity,
        "reference": "Synthetic inventory test",
    }
    if kind == "receipt":
        data["to_location_id"] = locations[0]["id"]
    if kind in ("dispatch", "block", "unblock", "reserve", "transfer"):
        data["from_location_id"] = locations[0]["id"]
    if kind == "transfer":
        data["to_location_id"] = locations[1]["id"]
    if kind == "reserve":
        data["expires_at"] = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    data.update(fields)
    return create(client, tokens[token], "inventory/drafts", data)


def post(env, row, expected=200, token=0, key=None):
    client, tokens, *_ = env
    result = client.post(
        "/api/v1/inventory/drafts/" + row["id"] + "/post",
        headers={**tokens[token], "Idempotency-Key": key or str(uuid4())},
    )
    assert result.status_code == expected, result.text
    return result.json()


def balance(env, location_index=0, token=0):
    client, tokens, _, _, _, locations, _, lot, _ = env
    items = client.get(
        "/api/v1/inventory/balances?lot_id=" + lot["id"], headers=tokens[token]
    ).json()["items"]
    row = next((r for r in items if r["location_id"] == locations[location_index]["id"]), {})
    return tuple(Decimal(row.get(k, "0")) for k in ("on_hand", "blocked", "reserved", "available"))


def test_drafts_ownership_permissions_and_posting_idempotency(inventory, catalog):
    env = inventory
    client, tokens, orgs, users, warehouses, locations, party, lot, lot_data = env
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2], headers=tokens[0], json={"role": "editor"}
        ).status_code
        == 200
    )
    create(
        client,
        tokens[2],
        "inventory/drafts",
        {
            "lot_id": lot["id"],
            "kind": "receipt",
            "quantity": "10",
            "to_location_id": locations[0]["id"],
            "reference": "No warehouse grant",
        },
        expected=404,
    )
    create(
        client,
        tokens[0],
        "warehouse-access",
        {"user_id": users[2], "warehouse_id": warehouses[0]["id"]},
    )
    row = draft(env, "receipt", token=2)
    assert row["status"] == "draft" and balance(env) == (0, 0, 0, 0)
    post(env, row, 403, token=2)
    first = post(env, row, key="post-retry")
    assert post(env, row, key="post-retry") == first
    assert post(env, row)["id"] == first["id"]
    assert balance(env) == (10, 0, 0, 10)
    entries = client.get("/api/v1/inventory/entries", headers=tokens[0]).json()
    assert entries["total"] == 1
    assert lot["owner_party_id"] == party["id"] and lot["owner_kind"] == "party"
    assert (
        client.put(
            "/api/v1/inventory/lots/" + lot["id"], headers=tokens[0], json={"owner_kind": "company"}
        ).status_code
        == 405
    )
    create(
        client,
        tokens[0],
        "inventory/lots",
        {**lot_data, "code": "BAD", "owner_party_id": None},
        expected=422,
    )
    create(
        client,
        tokens[0],
        "inventory/lots",
        {**lot_data, "code": "BAD", "owner_kind": "company"},
        expected=422,
    )
    create(
        client,
        tokens[0],
        "inventory/lots",
        {**lot_data, "code": "BAD", "unit": "tonne"},
        expected=409,
    )
    assert (
        client.put(
            "/api/v1/products/" + catalog[2]["id"],
            headers=tokens[0],
            json={**catalog[1], "unit": "tonne"},
        ).status_code
        == 409
    )
    # Each legal owner has an independent position even in the same physical location.
    company = create(
        client,
        tokens[0],
        "inventory/lots",
        {**lot_data, "code": "COMPANY", "owner_kind": "company", "owner_party_id": None},
    )
    empty = draft(env, "dispatch", "1", lot_id=company["id"])
    post(env, empty, 409)
    assert client.get("/api/v1/inventory/lots", headers=tokens[1]).json()["total"] == 0
    assert client.get("/api/v1/inventory/drafts/" + row["id"], headers=tokens[1]).status_code == 404
    post(env, row, 404, token=1)
    for resource in ("lots", "drafts", "entries", "reservations", "balances"):
        assert client.get("/api/v1/inventory/" + resource, headers=tokens[1]).json()["total"] == 0


def test_transfers_blocks_and_compensating_reversals(inventory):
    env = inventory
    client, tokens, _, _, _, _, _, lot, _ = env
    receipt = draft(env, "receipt", "20")
    post(env, receipt)
    blocked = draft(env, "block", "4")
    post(env, blocked)
    post(env, draft(env, "dispatch", "17"), 409)
    transfer = draft(env, "transfer", "10")
    post(env, transfer)
    assert balance(env) == (10, 4, 0, 6) and balance(env, 1) == (10, 0, 0, 10)
    post(env, draft(env, "unblock", "5"), 409)
    post(env, draft(env, "unblock", "2"))
    assert balance(env) == (10, 2, 0, 8)
    reverse = draft(env, "reversal", "10", reverses_id=transfer["id"])
    post(env, reverse)
    assert balance(env) == (20, 2, 0, 18) and balance(env, 1) == (0, 0, 0, 0)
    post(env, draft(env, "reversal", "10", reverses_id=transfer["id"]), 409)
    post(
        env, draft(env, "reversal", "20", reverses_id=receipt["id"]), 409
    )  # Blocked stock remains.
    create(
        client,
        tokens[0],
        "inventory/drafts",
        {
            "lot_id": lot["id"],
            "kind": "reversal",
            "quantity": "10",
            "reverses_id": reverse["id"],
            "reference": "Reverse a reversal",
        },
        expected=422,
    )
    rejected = draft(env, "dispatch", "1")
    result = client.post(
        "/api/v1/inventory/drafts/" + rejected["id"] + "/reject",
        headers={**tokens[0], "Idempotency-Key": "reject-once"},
    )
    assert result.status_code == 200 and result.json()["status"] == "rejected"
    post(env, rejected, 409)
    assert (
        client.delete("/api/v1/inventory/drafts/" + receipt["id"], headers=tokens[0]).status_code
        == 405
    )
    with Session(engine()) as db:
        posted = db.scalar(select(m.StockDraft).where(m.StockDraft.id == UUID(receipt["id"])))
        posted.quantity = Decimal("1")
        with pytest.raises(IntegrityError):
            db.commit()
    for table in ("inventory_entries", "inventory_lots"):
        with engine().connect() as conn:
            with pytest.raises(IntegrityError):
                conn.execute(text(f"DELETE FROM {table}"))
            conn.rollback()


def test_reservation_lifecycle_expiry_and_reversal(inventory, monkeypatch):
    env = inventory
    client, tokens, *_ = env
    post(env, draft(env, "receipt", "10"))
    hold = draft(env, "reserve", "6")
    reservation_id = post(env, hold)["reservation_id"]
    assert balance(env) == (10, 0, 6, 4)
    post(env, draft(env, "block", "5"), 409)
    fulfilled = draft(env, "fulfill", "2", reservation_id=reservation_id)
    post(env, fulfilled)
    assert balance(env) == (8, 0, 4, 4)
    post(env, draft(env, "reversal", "2", reverses_id=fulfilled["id"]))
    assert balance(env) == (10, 0, 6, 4)
    post(env, draft(env, "release", "1", reservation_id=reservation_id))
    assert balance(env) == (10, 0, 5, 5)
    post(
        env, draft(env, "reversal", "6", reverses_id=hold["id"]), 409
    )  # Reservation has a dependent release.
    future = datetime.now(UTC) + timedelta(hours=2)
    monkeypatch.setattr(service, "now", lambda db: future)
    assert balance(env) == (10, 0, 0, 10)
    post(env, draft(env, "fulfill", "1", reservation_id=reservation_id), 409)
    post(env, draft(env, "reserve", "2"), 409)  # Expired before approval.
    post(env, draft(env, "release", "5", reservation_id=reservation_id))
    reservations = client.get("/api/v1/inventory/reservations", headers=tokens[0]).json()["items"]
    assert (
        len(reservations) == 1
        and Decimal(reservations[0]["remaining"]) == 0
        and reservations[0]["expired"]
    )
    with engine().connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(text("UPDATE inventory_reservations SET quantity=1"))
        conn.rollback()


@pytest.mark.parametrize("kind", ["dispatch", "reserve", "transfer"])
def test_concurrent_postings_cannot_overspend_stock(inventory, kind):
    env = inventory
    client, tokens, _, users, *_ = env
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2], headers=tokens[0], json={"role": "admin"}
        ).status_code
        == 200
    )
    post(env, draft(env, "receipt", "10"))
    rows = [draft(env, kind, "7"), draft(env, kind, "7")]

    def attempt(pair):
        index, token = pair
        return client.post(
            "/api/v1/inventory/drafts/" + rows[index]["id"] + "/post",
            headers={**tokens[token], "Idempotency-Key": str(uuid4())},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [(0, 0), (1, 2)]))
    assert sorted(results) == [200, 409]
    expected = (10, 0, 7, 3) if kind == "reserve" else (3, 0, 0, 3)
    assert balance(env) == expected
    if kind == "reserve":
        assert client.get("/api/v1/inventory/reservations", headers=tokens[0]).json()["total"] == 1
    if kind == "transfer":
        assert balance(env, 1) == (7, 0, 0, 7)


def test_inventory_validation_warehouse_visibility_and_database_constraints(inventory):
    env = inventory
    client, tokens, orgs, users, warehouses, locations, _, lot, lot_data = env
    base = {
        "lot_id": lot["id"],
        "kind": "receipt",
        "quantity": "2",
        "to_location_id": locations[0]["id"],
        "reference": "Test",
    }
    for bad in ("0", "-1", "NaN", "Infinity", "1.0001", 1.5, True):
        create(client, tokens[0], "inventory/drafts", {**base, "quantity": bad}, expected=422)
    create(
        client, tokens[0], "inventory/drafts", {**base, "organization_id": orgs[1]}, expected=422
    )
    create(client, tokens[1], "inventory/drafts", base, expected=404)
    create(
        client,
        tokens[0],
        "inventory/drafts",
        {**base, "from_location_id": locations[0]["id"]},
        expected=422,
    )
    post(env, draft(env, "receipt", "10"))
    transfer = draft(env, "transfer", "3")
    post(env, transfer)
    assert client.get("/api/v1/inventory/balances", headers=tokens[2]).json()["total"] == 0
    assert client.get("/api/v1/inventory/lots", headers=tokens[2]).json()["total"] == 0
    create(
        client,
        tokens[0],
        "warehouse-access",
        {"user_id": users[2], "warehouse_id": warehouses[0]["id"]},
    )
    assert balance(env, token=2) == (7, 0, 0, 7)
    assert client.get("/api/v1/inventory/balances", headers=tokens[2]).json()["total"] == 1
    assert (
        client.get("/api/v1/inventory/drafts/" + transfer["id"], headers=tokens[2]).status_code
        == 404
    )
    assert client.get("/api/v1/inventory/entries", headers=tokens[2]).json()["total"] == 2
    with Session(engine()) as db:
        db.add(
            m.StockLot(
                organization_id=UUID(orgs[1]),
                code="CROSS",
                product_id=UUID(lot_data["product_id"]),
                owner_kind="company",
                unit="kg",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    with Session(engine()) as db:
        db.add(
            m.StockEntry(
                organization_id=UUID(orgs[0]),
                draft_id=UUID(draft(env, "receipt")["id"]),
                lot_id=UUID(lot["id"]),
                warehouse_id=UUID(warehouses[0]["id"]),
                location_id=UUID(locations[0]["id"]),
                on_hand_delta=Decimal("1"),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize("target", ["products", "parties", "warehouses"])
def test_posting_rechecks_master_status_after_concurrent_deactivation(inventory, target):
    from time import monotonic, sleep

    env = inventory
    client, tokens, _, _, warehouses, _, party, _, lot_data = env
    ids = {
        "products": lot_data["product_id"],
        "parties": party["id"],
        "warehouses": warehouses[0]["id"],
    }
    movement = draft(env, "receipt", "2")
    with engine().connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(text(f"UPDATE {target} SET active=false WHERE id=:id"), {"id": ids[target]})
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.post,
                "/api/v1/inventory/drafts/" + movement["id"] + "/post",
                headers={**tokens[0], "Idempotency-Key": str(uuid4())},
            )
            try:
                deadline = monotonic() + 5
                with engine().connect() as observer:
                    while monotonic() < deadline:
                        observer.commit()
                        waiting = observer.scalar(
                            text("""
                            SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                            WHERE datname=current_database() AND wait_event_type='Lock'
                              AND query LIKE :query)
                        """),
                            {"query": "%" + target + "%"},
                        )
                        if pending.done() or waiting:
                            break
                        sleep(0.01)
                    else:
                        pytest.fail("Posting neither completed nor waited for master status")
            finally:
                transaction.commit()
            response = pending.result(timeout=5)
    assert response.status_code == 409, response.text
    assert balance(env) == (0, 0, 0, 0)
    assert (
        client.get("/api/v1/inventory/drafts/" + movement["id"], headers=tokens[0]).json()["status"]
        == "draft"
    )


@pytest.mark.parametrize("resource", ["locations", "inventory/drafts"])
def test_warehouse_revocation_blocks_queued_editor_mutation(inventory, resource):
    from time import monotonic, sleep

    env = inventory
    client, tokens, _, users, warehouses, locations, _, lot, _ = env
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2], headers=tokens[0], json={"role": "editor"}
        ).status_code
        == 200
    )
    grant = create(
        client,
        tokens[0],
        "warehouse-access",
        {"user_id": users[2], "warehouse_id": warehouses[0]["id"]},
    )
    payload = (
        {"warehouse_id": warehouses[0]["id"], "code": "queued", "name": "Queued", "kind": "hall"}
        if resource == "locations"
        else {
            "lot_id": lot["id"],
            "kind": "receipt",
            "quantity": "2",
            "to_location_id": locations[0]["id"],
            "reference": "Queued",
        }
    )
    with engine().connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(text("DELETE FROM warehouse_access WHERE id=:id"), {"id": grant["id"]})
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(
                client.post,
                "/api/v1/" + resource,
                headers={**tokens[2], "Idempotency-Key": "revoked-grant"},
                json=payload,
            )
            try:
                deadline = monotonic() + 5
                with engine().connect() as observer:
                    while monotonic() < deadline:
                        observer.commit()
                        waiting = observer.scalar(
                            text("""SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                            WHERE datname=current_database() AND wait_event_type='Lock'
                            AND query LIKE '%warehouse_access%')""")
                        )
                        if pending.done() or waiting:
                            break
                        sleep(0.01)
                    else:
                        pytest.fail("Editor mutation did not execute")
            finally:
                transaction.commit()
            response = pending.result(timeout=5)
    assert response.status_code == 403, response.text
    assert client.get("/api/v1/inventory/drafts", headers=tokens[0]).json()["total"] == 0
    assert client.get("/api/v1/locations", headers=tokens[0]).json()["total"] == 2


@pytest.mark.parametrize("resource", ["locations", "inventory/drafts"])
def test_idempotent_replay_does_not_restore_revoked_warehouse_access(inventory, resource):
    env = inventory
    client, tokens, _, users, warehouses, locations, _, lot, _ = env
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2], headers=tokens[0], json={"role": "editor"}
        ).status_code
        == 200
    )
    grant_data = {"user_id": users[2], "warehouse_id": warehouses[0]["id"]}
    grant = create(client, tokens[0], "warehouse-access", grant_data)
    payload = (
        {"warehouse_id": warehouses[0]["id"], "code": "replay", "name": "Replay", "kind": "hall"}
        if resource == "locations"
        else {
            "lot_id": lot["id"],
            "kind": "receipt",
            "quantity": "2",
            "to_location_id": locations[0]["id"],
            "reference": "Replay",
        }
    )
    headers = {**tokens[2], "Idempotency-Key": "warehouse-replay"}
    first = client.post("/api/v1/" + resource, headers=headers, json=payload)
    assert first.status_code == 201
    assert (
        client.delete("/api/v1/warehouse-access/" + grant["id"], headers=tokens[0]).status_code
        == 200
    )
    assert (
        client.get("/api/v1/" + resource + "/" + first.json()["id"], headers=tokens[2]).status_code
        == 404
    )
    replay = client.post("/api/v1/" + resource, headers=headers, json=payload)
    assert replay.status_code == 404, replay.text
    create(client, tokens[0], "warehouse-access", grant_data)
    restored = client.post("/api/v1/" + resource, headers=headers, json=payload)
    assert restored.status_code == 201 and restored.json() == first.json()
    assert client.get("/api/v1/" + resource, headers=tokens[0]).json()["total"] == (
        3 if resource == "locations" else 1
    )
