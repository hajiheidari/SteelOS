from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID, uuid4

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
    with localcontext() as decimal_ctx:
        decimal_ctx.prec = 60
        base = Decimal(quantity) * Decimal(huge_price["amount"])
        base = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        tax = (base / 10).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        assert huge["subtotal"] == format(base, ".2f")
        assert huge["tax_total"] == format(tax, ".2f")
        assert huge["grand_total"] == format(base + tax, ".2f")
    assert listed["tax_total"] == huge["tax_total"]
    assert listed["grand_total"] == huge["grand_total"]
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


def test_invoice_policy_preserves_exact_fractional_totals_and_explicit_currency(sales):
    client, tokens, *_, price_data, payload = sales
    for currency in ("IRR", "IRT", "USD", "EUR"):
        lines = []
        for amount in ("0.000001", "0.000002"):
            price = create(
                client,
                tokens[0],
                "price-observations",
                {**price_data, "currency": currency, "amount": amount},
            )
            response = client.post(
                f"/api/v1/price-observations/{price['id']}/decision",
                headers=tokens[0],
                json={"status": "approved"},
            )
            assert response.status_code == 200
            lines.append({"price_id": price["id"], "quantity": "0.001"})
        draft = create_draft(
            sales,
            {
                **payload,
                "code": f"EXACT-{currency}",
                "currency": currency,
                "lines": lines,
            },
        )
        assert [line["estimated_amount"] for line in draft["lines"]] == [
            "0.000000001",
            "0.000000002",
        ]
        assert draft["estimated_total"] == "0.000000003"
        assert draft["currency"] == currency  # Never convert rials/tomans/FX implicitly.
        assert draft["invoice_policy"] == {
            "version": "iran-invoice-v3",
            "currency": "IRR",
            "rounding": "half_up",
            "decimal_places": 2,
            "calculation": "per_line",
            "currency_matches": currency == "IRR",
            "tax_workflow": "exclusive",
        }
        listed = client.get(
            f"/api/v1/sales-drafts?q=EXACT-{currency}",
            headers=tokens[0],
        ).json()["items"][0]
        assert listed["estimated_total"] == draft["estimated_total"]
        assert listed["invoice_policy"] == draft["invoice_policy"]
        revision = client.get(
            f"/api/v1/sales-drafts/{draft['id']}/revisions/1",
            headers=tokens[0],
        ).json()
        assert revision["snapshot"]["invoice_policy"] == draft["invoice_policy"]
        assert draft["financial_approval"] is False


def test_tax_defaults_are_scoped_versioned_and_do_not_reprice_existing_drafts(sales):
    client, tokens, orgs, *_rest, payload = sales
    path = "/api/v1/organization/tax-policy"
    policy = client.get(path, headers=tokens[0]).json()
    assert policy["tax_rate_percent"] == "10.000000"
    draft = create_draft(sales)
    assert draft["tax_rate_percent"] == "10.000000"
    assert draft["tax_total"] == "26209.74"
    assert draft["grand_total"] == "288307.09"
    change = {"tax_rate_percent": "9.123456", "expected_version": policy["version"]}
    assert client.put(path, headers=tokens[2], json=change).status_code == 403
    response = client.put(path, headers=tokens[0], json=change)
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 2
    assert client.put(path, headers=tokens[0], json=change).status_code == 409
    assert client.get(path, headers=tokens[1]).json()["tax_rate_percent"] == "10.000000"
    assert (
        client.get(f"/api/v1/sales-drafts/{draft['id']}", headers=tokens[0]).json()["grand_total"]
        == draft["grand_total"]
    )
    another = create_draft(sales, {**payload, "code": "NEW-RATE"})
    assert another["tax_rate_percent"] == "9.123456"
    edited = client.put(
        f"/api/v1/sales-drafts/{draft['id']}",
        headers={**tokens[0], "Idempotency-Key": str(uuid4())},
        json={**payload, "expected_version": 1, "tax_rate_percent": "0"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["tax_total"] == "0.00"
    assert edited.json()["grand_total"] == "262097.35"
    old = client.get(f"/api/v1/sales-drafts/{draft['id']}/revisions/1", headers=tokens[0]).json()
    assert old["snapshot"] == draft
    with Session(engine()) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(
                    m.AuditEvent.organization_id == orgs[0],
                    m.AuditEvent.action == "update_tax_policy",
                )
            )
            == 1
        )


def test_tax_rejects_inexact_inputs_and_inclusive_prices_without_double_tax(sales):
    client, tokens, *_, price_data, payload = sales
    for rate in (-1, "100.000001", "0.0000001", "NaN", "Infinity", True, 9.5):
        create_draft(sales, {**payload, "tax_rate_percent": rate}, expected=422)
        assert (
            client.put(
                "/api/v1/organization/tax-policy",
                headers=tokens[0],
                json={"expected_version": 1, "tax_rate_percent": rate},
            ).status_code
            == 422
        )
    price = create(
        client,
        tokens[0],
        "price-observations",
        {
            **price_data,
            "tax_included": True,
        },
    )
    assert (
        client.post(
            f"/api/v1/price-observations/{price['id']}/decision",
            headers=tokens[0],
            json={"status": "approved"},
        ).status_code
        == 200
    )
    create_draft(
        sales,
        {
            **payload,
            "lines": [{"price_id": price["id"], "quantity": "1"}],
        },
        expected=409,
    )
    listed = client.get(
        "/api/v1/price-observations?approved_only=true&tax_included=false",
        headers=tokens[0],
    ).json()
    assert price["id"] not in {row["id"] for row in listed["items"]}
    assert client.get("/api/v1/products?tax_included=false", headers=tokens[0]).status_code == 422
    assert service.financial_line(Decimal("0.000000001"), Decimal("0.000001"), "half_up_2") == {
        "base_amount": "0.00",
        "tax_total": "0.00",
        "grand_total": "0.00",
    }


def test_legacy_draft_tax_is_unconfigured_until_an_explicit_new_edit(sales):
    client, tokens, orgs, users, *_, payload = sales
    original = create_draft(sales)
    legacy_ids = []
    with Session(engine()) as db:
        template = db.scalar(
            select(m.SalesDraftLine).where(
                m.SalesDraftLine.draft_id == original["id"],
            )
        )
        for code in ("LEGACY-EDIT", "LEGACY-CANCEL"):
            draft = m.SalesDraft(
                organization_id=UUID(orgs[0]),
                customer_id=UUID(payload["customer_id"]),
                code=code,
                currency="IRR",
                created_by=UUID(users[0]),
                updated_by=UUID(users[0]),
            )
            db.add(draft)
            db.flush()
            db.add(
                m.SalesDraftLine(
                    organization_id=draft.organization_id,
                    draft_id=draft.id,
                    **{
                        key: getattr(template, key)
                        for key in (
                            "position",
                            "product_id",
                            "price_id",
                            "source_id",
                            "quantity",
                            "unit_price",
                            "unit",
                            "price_valid_until",
                            "snapshot",
                        )
                    },
                )
            )
            db.add(
                m.SalesDraftRevision(
                    organization_id=draft.organization_id,
                    draft_id=draft.id,
                    version=1,
                    actor_id=UUID(users[0]),
                    snapshot={"legacy": True},
                )
            )
            legacy_ids.append(str(draft.id))
        db.commit()
    for draft_id in legacy_ids:
        legacy = client.get(f"/api/v1/sales-drafts/{draft_id}", headers=tokens[0]).json()
        assert legacy["tax_rate_percent"] is None
        assert legacy["tax_total"] is None and legacy["grand_total"] is None
    edited = client.put(
        f"/api/v1/sales-drafts/{legacy_ids[0]}",
        headers={**tokens[0], "Idempotency-Key": str(uuid4())},
        json={**payload, "code": "LEGACY-EDIT", "note": "new note", "expected_version": 1},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["tax_rate_percent"] == "10.000000"
    cancelled = client.post(
        f"/api/v1/sales-drafts/{legacy_ids[1]}/cancel",
        headers={**tokens[0], "Idempotency-Key": str(uuid4())},
        json={"expected_version": 1},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["tax_rate_percent"] is None
    for draft_id in legacy_ids:
        old = client.get(f"/api/v1/sales-drafts/{draft_id}/revisions/1", headers=tokens[0]).json()
        assert old["snapshot"] == {"legacy": True}


def test_concurrent_tax_policy_edits_cannot_overwrite_the_same_version(world):
    client, tokens, _, users = world
    assert (
        client.put(
            f"/api/v1/organization/members/{users[2]}",
            headers=tokens[0],
            json={"role": "admin"},
        ).status_code
        == 200
    )

    def update(index):
        return client.put(
            "/api/v1/organization/tax-policy",
            headers=tokens[index],
            json={"tax_rate_percent": str(8 + index), "expected_version": 1},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(update, [0, 2])) == [200, 409]
    assert client.get("/api/v1/organization/tax-policy", headers=tokens[0]).json()["version"] == 2


def test_half_up_two_decimal_lines_tax_and_totals_agree_between_sql_and_decimal(sales):
    client, tokens, *_, price_data, payload = sales
    for value, expected in (("123.454", "123.45"), ("123.455", "123.46"), ("123.456", "123.46")):
        assert (
            service.financial_line(Decimal(value), Decimal("0"), "half_up_2")["base_amount"]
            == expected
        )
    lines = []
    for _ in range(2):
        price = create(client, tokens[0], "price-observations", {**price_data, "amount": "0.045"})
        assert (
            client.post(
                f"/api/v1/price-observations/{price['id']}/decision",
                headers=tokens[0],
                json={"status": "approved"},
            ).status_code
            == 200
        )
        lines.append({"price_id": price["id"], "quantity": "1"})
    draft = create_draft(sales, {**payload, "lines": lines})
    assert draft["amount_rounding"] == "half_up_2"
    assert draft["estimated_total"] == "0.090000000"  # Raw evidence stays exact.
    assert draft["subtotal"] == "0.10"
    assert draft["tax_total"] == "0.02"
    assert draft["grand_total"] == "0.12"
    for line in draft["lines"]:
        assert line["base_amount"] == "0.05"
        assert line["tax_total"] == "0.01"
        assert line["grand_total"] == "0.06"
    listed = client.get("/api/v1/sales-drafts", headers=tokens[0]).json()["items"][0]
    for key in ("subtotal", "tax_total", "grand_total"):
        assert listed[key] == draft[key]
    assert (
        create_draft(
            sales, {**payload, "code": "RATE-MAX", "lines": lines, "tax_rate_percent": "100"}
        )["tax_total"]
        == "0.10"
    )
