from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from uuid import uuid4

import pytest
from app import models as m
from app.db import engine
from app.modules.sales import service
from conftest import create
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def sales(world, catalog):
    client, tokens, orgs, users = world
    customer = create(
        client,
        tokens[0],
        "parties",
        {"name": "مشتری فروش", "kind": "legal_entity", "roles": ["customer", "supplier"]},
    )
    source = create(
        client,
        tokens[0],
        "price-sources",
        {
            "code": "sales",
            "name": "منبع فروش",
            "kind": "manual",
            "approved": True,
            "provenance": "منشأ مجاز",
        },
    )
    at = datetime.now(UTC)
    price_data = {
        "product_id": catalog[2]["id"],
        "source_id": source["id"],
        "amount": "123456.123456",
        "currency": "IRR",
        "unit": "kg",
        "observed_at": (at - timedelta(minutes=1)).isoformat(),
        "valid_until": (at + timedelta(hours=1)).isoformat(),
        "delivery_location": "تهران",
        "delivery_terms": "درب انبار",
        "tax_included": False,
        "provenance": "قیمت دستی مجاز",
    }
    price = create(client, tokens[0], "price-observations", price_data)
    assert (
        client.post(
            "/api/v1/price-observations/" + price["id"] + "/decision",
            headers=tokens[0],
            json={"status": "approved"},
        ).status_code
        == 200
    )
    payload = {
        "code": "QUOTE-1",
        "customer_id": customer["id"],
        "currency": "IRR",
        "note": "برآورد داخلی",
        "lines": [{"price_id": price["id"], "quantity": "2.123"}],
    }
    return client, tokens, orgs, users, customer, source, price, price_data, payload


def create_draft(env, payload=None, *, token=0, key=None, expected=201):
    client, tokens, *_, base = env
    return create(
        client, tokens[token], "sales-drafts", payload or base, key=key, expected=expected
    )


def test_sales_snapshots_exact_estimate_scope_replay_and_revision_history(sales):
    client, tokens, orgs, users, customer, source, price, _, payload = sales
    draft = create_draft(sales, key="sales-once")
    assert draft["estimated_total"] == "262097.350097088"
    assert (
        draft["status"] == "draft"
        and draft["version"] == 1
        and draft["financial_approval"] is False
    )
    assert draft["lines"][0]["snapshot"]["price"]["delivery_terms"] == "درب انبار"
    assert draft["lines"][0]["snapshot"]["source"]["provenance"] == source["provenance"]
    assert create_draft(sales, key="sales-once") == draft
    create_draft(sales, {**payload, "note": "different"}, key="sales-once", expected=409)
    create_draft(sales, token=2, expected=403)
    create_draft(sales, token=1, expected=404)
    assert client.get("/api/v1/sales-drafts", headers=tokens[1]).json()["total"] == 0
    assert client.get("/api/v1/sales-drafts/" + draft["id"], headers=tokens[1]).status_code == 404
    listed = client.get("/api/v1/sales-drafts?q=مشتری", headers=tokens[0]).json()
    assert (
        listed["total"] == 1 and listed["items"][0]["estimated_total"] == draft["estimated_total"]
    )
    updated = client.put(
        "/api/v1/sales-drafts/" + draft["id"],
        headers={**tokens[0], "Idempotency-Key": "sales-edit"},
        json={
            **payload,
            "expected_version": 1,
            "lines": [{"price_id": price["id"], "quantity": "3"}],
        },
    )
    assert updated.status_code == 200, updated.text
    assert (
        updated.json()["version"] == 2 and updated.json()["estimated_total"] == "370368.370368000"
    )
    assert (
        client.get(f"/api/v1/sales-drafts/{draft['id']}/revisions", headers=tokens[0]).json()[
            "total"
        ]
        == 2
    )
    first = client.get(f"/api/v1/sales-drafts/{draft['id']}/revisions/1", headers=tokens[0]).json()
    assert first["snapshot"] == draft
    assert (
        client.get(f"/api/v1/sales-drafts/{draft['id']}/revisions/1", headers=tokens[1]).status_code
        == 404
    )
    assert (
        client.delete("/api/v1/sales-drafts/" + draft["id"], headers=tokens[0]).status_code == 405
    )
    assert (
        client.post(f"/api/v1/sales-drafts/{draft['id']}/approve", headers=tokens[0]).status_code
        == 404
    )
    cancelled = client.post(
        f"/api/v1/sales-drafts/{draft['id']}/cancel",
        headers={**tokens[0], "Idempotency-Key": "sales-cancel"},
        json={"expected_version": 2},
    )
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert (
        client.put(
            "/api/v1/sales-drafts/" + draft["id"],
            headers={**tokens[0], "Idempotency-Key": str(uuid4())},
            json={**payload, "expected_version": 3},
        ).status_code
        == 409
    )
    for statement in (
        "DELETE FROM sales_drafts",
        "UPDATE sales_draft_revisions SET version=99",
        "DELETE FROM sales_draft_lines",
    ):
        with engine().connect() as connection:
            with pytest.raises(IntegrityError):
                connection.execute(text(statement))
            connection.rollback()
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(m.StockEntry)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(m.AuditEvent.resource == "sales-drafts")
            )
            == 3
        )


def test_sales_validation_price_liveness_and_precision(sales, monkeypatch):
    client, tokens, _, _, customer, source, price, price_data, payload = sales
    for invalid in (0, "-1", "NaN", "Infinity", "1.0001", 1.2, True):
        create_draft(
            sales,
            {**payload, "lines": [{"price_id": price["id"], "quantity": invalid}]},
            expected=422,
        )
    create_draft(sales, {**payload, "currency": "IRT"}, expected=422)
    create_draft(sales, {**payload, "lines": payload["lines"] * 2}, expected=422)
    create_draft(sales, {**payload, "organization_id": str(uuid4())}, expected=422)
    pending = create(client, tokens[0], "price-observations", price_data)
    create_draft(
        sales, {**payload, "lines": [{"price_id": pending["id"], "quantity": "1"}]}, expected=409
    )
    draft = create_draft(sales)
    monkeypatch.setattr(service, "now", lambda db: datetime.now(UTC) + timedelta(hours=2))
    read = client.get("/api/v1/sales-drafts/" + draft["id"], headers=tokens[0]).json()
    assert not read["prices_usable"] and read["estimated_total"] == draft["estimated_total"]
    assert read["lines"][0]["snapshot"] == draft["lines"][0]["snapshot"]
    create_draft(sales, {**payload, "code": "EXPIRED"}, expected=409)
    monkeypatch.undo()
    assert (
        client.put(
            "/api/v1/price-sources/" + source["id"],
            headers=tokens[0],
            json={key: source[key] for key in ("code", "name", "kind", "provenance")}
            | {"approved": False},
        ).status_code
        == 200
    )
    assert not client.get("/api/v1/sales-drafts/" + draft["id"], headers=tokens[0]).json()[
        "prices_usable"
    ]
    create_draft(sales, {**payload, "code": "UNAPPROVED"}, expected=409)
    assert (
        client.post(
            f"/api/v1/sales-drafts/{draft['id']}/cancel",
            headers={**tokens[0], "Idempotency-Key": str(uuid4())},
            json={"expected_version": 1},
        ).status_code
        == 200
    )
    with localcontext() as decimal_ctx:
        decimal_ctx.prec = 60
        quantity = Decimal("99999999999999999.999")
        unit_price = Decimal("999999999999999999.999999")
        assert service.estimate(quantity, unit_price) == quantity * unit_price
        assert len(str(service.estimate(quantity, unit_price)).replace(".", "")) > 28


def test_sales_optimistic_concurrency_between_editors(sales):
    client, tokens, _, users, _, _, _, _, payload = sales
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2], headers=tokens[0], json={"role": "editor"}
        ).status_code
        == 200
    )
    draft = create_draft(sales)

    def update(index):
        return client.put(
            "/api/v1/sales-drafts/" + draft["id"],
            headers={**tokens[index], "Idempotency-Key": str(uuid4())},
            json={**payload, "expected_version": 1, "note": f"actor {index}"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, [0, 2])) == [200, 409]
    assert (
        client.get("/api/v1/sales-drafts/" + draft["id"], headers=tokens[0]).json()["version"] == 2
    )
    assert (
        client.get(f"/api/v1/sales-drafts/{draft['id']}/revisions", headers=tokens[0]).json()[
            "total"
        ]
        == 2
    )


def test_sales_customer_policy_unit_precision_and_tenant_foreign_keys(sales):
    from uuid import UUID

    client, tokens, orgs, users, customer, _, _, price_data, payload = sales
    supplier = create(
        client,
        tokens[0],
        "parties",
        {"name": "تأمین‌کننده", "kind": "individual", "roles": ["supplier"]},
    )
    create_draft(sales, {**payload, "customer_id": supplier["id"]}, expected=409)
    customer_data = {
        key: customer[key]
        for key in ("name", "kind", "roles", "registration_id", "contacts", "addresses")
    }
    assert (
        client.put(
            "/api/v1/parties/" + customer["id"],
            headers=tokens[0],
            json={**customer_data, "active": False},
        ).status_code
        == 200
    )
    create_draft(sales, expected=409)
    assert (
        client.put(
            "/api/v1/parties/" + customer["id"],
            headers=tokens[0],
            json={**customer_data, "active": True},
        ).status_code
        == 200
    )
    piece = create(client, tokens[0], "price-observations", {**price_data, "unit": "piece"})
    assert (
        client.post(
            "/api/v1/price-observations/" + piece["id"] + "/decision",
            headers=tokens[0],
            json={"status": "approved"},
        ).status_code
        == 200
    )
    create_draft(
        sales, {**payload, "lines": [{"price_id": piece["id"], "quantity": "0.5"}]}, expected=422
    )
    whole = create_draft(sales, {**payload, "lines": [{"price_id": piece["id"], "quantity": "2"}]})
    assert (
        whole["lines"][0]["unit"] == "piece"
    )  # Explicit price unit; no implicit stock-unit conversion.
    huge_price = create(
        client,
        tokens[0],
        "price-observations",
        {**price_data, "amount": "999999999999999999.999999"},
    )
    assert (
        client.post(
            "/api/v1/price-observations/" + huge_price["id"] + "/decision",
            headers=tokens[0],
            json={"status": "approved"},
        ).status_code
        == 200
    )
    quantity = "99999999999999999.999"
    huge = create_draft(
        sales,
        {
            **payload,
            "code": "PRECISE",
            "lines": [{"price_id": huge_price["id"], "quantity": quantity}],
        },
    )
    with localcontext() as decimal_ctx:
        decimal_ctx.prec = 60
        assert huge["estimated_total"] == format(
            Decimal(quantity) * Decimal(huge_price["amount"]), ".9f"
        )
    listed = client.get("/api/v1/sales-drafts?q=PRECISE", headers=tokens[0]).json()["items"][0]
    assert listed["estimated_total"] == huge["estimated_total"]
    assert (
        client.get("/api/v1/price-observations?currency=IRT", headers=tokens[0]).json()["total"]
        == 0
    )
    assert client.get("/api/v1/price-observations?q=قیمت", headers=tokens[0]).json()["total"] == 3
    with Session(engine()) as db:
        db.add(
            m.SalesDraft(
                organization_id=UUID(orgs[1]),
                customer_id=UUID(customer["id"]),
                code="CROSS",
                currency="IRR",
                created_by=UUID(users[1]),
                updated_by=UUID(users[1]),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize("master", ["source", "product", "customer"])
def test_sales_create_waits_for_master_revocation_without_partial_writes(sales, master):
    from time import monotonic, sleep

    client, tokens, _, _, customer, source, price, _, payload = sales
    table, field, row_id = {
        "source": ("price_sources", "approved", source["id"]),
        "product": ("products", "active", price["product_id"]),
        "customer": ("parties", "active", customer["id"]),
    }[master]
    with engine().connect() as blocker:
        transaction = blocker.begin()
        blocker.execute(text(f"UPDATE {table} SET {field}=false WHERE id=:id"), {"id": row_id})
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(
                client.post,
                "/api/v1/sales-drafts",
                headers={**tokens[0], "Idempotency-Key": "sales-race"},
                json=payload,
            )
            try:
                deadline = monotonic() + 5
                with engine().connect() as observer:
                    while monotonic() < deadline:
                        observer.commit()
                        waiting = observer.scalar(
                            text("""SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                            WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE :query)"""),
                            {"query": "%" + table + "%"},
                        )
                        if waiting or request.done():
                            break
                        sleep(0.01)
                    else:
                        pytest.fail("Sales creation did not execute")
            finally:
                transaction.commit()
            response = request.result(timeout=5)
    assert response.status_code == 409, response.text
    with Session(engine()) as db:
        assert db.scalar(select(func.count()).select_from(m.SalesDraft)) == 0
        assert db.scalar(select(func.count()).select_from(m.SalesDraftRevision)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.IdempotencyRecord)
                .where(m.IdempotencyRecord.key == "sales-race")
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(m.AuditEvent.resource == "sales-drafts")
            )
            == 0
        )
