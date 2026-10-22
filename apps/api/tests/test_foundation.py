import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.db import engine
from app.models import AuditEvent, AuthSession, Product
from app.modules.pricing import MockPriceProvider
from conftest import create
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def test_auth_rotation_revocation_and_isolation(world):
    client, tokens, orgs, _ = world
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "user0@example.test",
                "password": "Strong-password-123",
                "organization_id": orgs[1],
            },
        ).status_code
        == 401
    )
    me = client.get("/api/v1/auth/me", headers=tokens[0]).json()
    assert me["organization"]["id"] == orgs[0]
    token = client.post("/api/v1/auth/refresh", headers=tokens[0]).json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=tokens[0]).status_code == 401
    headers = {"Authorization": "Bearer " + token}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    with Session(engine()) as db:
        assert not db.scalar(select(AuthSession).where(AuthSession.token_hash == token))


def test_rate_limit_and_secret_redaction(world):
    client, _, orgs, _ = world
    payload = {
        "email": "absent@example.test",
        "password": "Do-not-echo-this",
        "organization_id": orgs[0],
    }
    for _ in range(10):
        assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert client.post("/api/v1/auth/login", json=payload).status_code == 429
    result = client.post(
        "/api/v1/auth/login", json={**payload, "organization_id": "secret-not-a-uuid"}
    )
    assert result.status_code == 422
    assert "secret-not-a-uuid" not in result.text
    assert "Do-not-echo-this" not in result.text
    assert result.json()["error"]["request_id"] == result.headers["X-Request-ID"]


def test_catalog_validation_duplicates_and_tenant_isolation(world, catalog):
    client, tokens, orgs, _ = world
    category, payload, product = catalog
    create(client, tokens[0], "products", {**payload, "sku": "different"}, expected=409)
    create(client, tokens[0], "products", {**payload, "attributes": {}}, expected=422)
    create(
        client,
        tokens[0],
        "products",
        {**payload, "attributes": {"thickness": {"value": "-1", "unit": "mm"}}},
        expected=422,
    )
    create(
        client,
        tokens[0],
        "products",
        {**payload, "attributes": {"thickness": {"value": "3", "unit": "cm"}}},
        expected=422,
    )
    create(client, tokens[0], "products", {**payload, "organization_id": orgs[1]}, expected=422)
    create(client, tokens[1], "products", payload, expected=404)
    assert client.get("/api/v1/products", headers=tokens[1]).json()["items"] == []
    for method in ("get", "put", "delete"):
        kwargs = {"json": payload} if method == "put" else {}
        assert (
            getattr(client, method)(
                "/api/v1/products/" + product["id"], headers=tokens[1], **kwargs
            ).status_code
            == 404
        )
    create(client, tokens[2], "products", payload, expected=403)
    updated = client.put(
        "/api/v1/products/" + product["id"], headers=tokens[0], json={**payload, "name": "ویرایش"}
    )
    assert updated.status_code == 200
    assert (
        client.get("/api/v1/products?q=ویرایش&sort=sku&direction=asc", headers=tokens[0]).json()[
            "total"
        ]
        == 1
    )
    with Session(engine()) as db:
        db.add(
            Product(
                organization_id=uuid.UUID(orgs[1]),
                sku="BAD",
                name="Bad",
                category_id=uuid.UUID(category["id"]),
                unit="kg",
                attributes={},
                specification_hash="bad",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_idempotency_and_audit(world):
    client, tokens, _, _ = world
    data = {
        "name": "مشتری",
        "kind": "legal_entity",
        "roles": ["customer", "supplier"],
        "registration_id": "123",
    }
    first = create(client, tokens[0], "parties", data, key="retry")
    assert create(client, tokens[0], "parties", data, key="retry") == first
    create(client, tokens[0], "parties", {**data, "name": "different"}, key="retry", expected=409)
    create(client, tokens[0], "parties", data, expected=409)
    assert client.get("/api/v1/parties?role=supplier", headers=tokens[0]).json()["total"] == 1
    assert client.get("/api/v1/parties?limit=101", headers=tokens[0]).status_code == 422
    events = client.get("/api/v1/audit-events", headers=tokens[0]).json()["items"]
    assert len([e for e in events if e["resource"] == "parties" and e["action"] == "create"]) == 1
    assert (
        client.get("/api/v1/audit-events", headers=tokens[1]).json()["total"] == 1
    )  # own login only
    assert client.get("/api/v1/audit-events", headers=tokens[2]).status_code == 403
    assert client.delete("/api/v1/parties/" + first["id"], headers=tokens[0]).status_code == 200
    with Session(engine()) as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "delete"))


def test_warehouse_hierarchy_access_and_cycles(world):
    client, tokens, _, users = world
    wh = create(
        client,
        tokens[0],
        "warehouses",
        {"code": "WH1", "name": "انبار", "city": "تهران", "address": "نشانی"},
    )
    base = {"warehouse_id": wh["id"], "code": "A", "name": "سالن", "kind": "hall"}
    parent = create(client, tokens[0], "locations", base)
    child = create(client, tokens[0], "locations", {**base, "code": "B", "parent_id": parent["id"]})
    assert (
        client.put(
            "/api/v1/locations/" + parent["id"],
            headers=tokens[0],
            json={**base, "parent_id": child["id"]},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/warehouses", headers=tokens[2]).json()["total"] == 0
    create(client, tokens[0], "warehouse-access", {"warehouse_id": wh["id"], "user_id": users[2]})
    assert client.get("/api/v1/warehouses", headers=tokens[2]).json()["total"] == 1
    assert client.get("/api/v1/locations", headers=tokens[1]).json()["total"] == 0
    wh2 = create(
        client,
        tokens[0],
        "warehouses",
        {"code": "WH2", "name": "انبار دوم", "city": "قم", "address": "نشانی"},
    )
    create(
        client,
        tokens[0],
        "locations",
        {**base, "warehouse_id": wh2["id"], "parent_id": parent["id"]},
        expected=422,
    )
    assert client.delete("/api/v1/warehouses/" + wh["id"], headers=tokens[0]).status_code == 409


def test_price_workflow_history_and_mock_adapter(world, catalog):
    client, tokens, _, _ = world
    source = create(
        client,
        tokens[0],
        "price-sources",
        {
            "code": "manual",
            "name": "دستی",
            "kind": "manual",
            "provenance": "Operator entry",
            "approved": False,
        },
    )
    now = datetime.now(timezone.utc)
    data = {
        "source_id": source["id"],
        "product_id": catalog[2]["id"],
        "amount": "123456.123456",
        "currency": "IRR",
        "unit": "kg",
        "observed_at": (now - timedelta(minutes=1)).isoformat(),
        "valid_until": (now + timedelta(hours=1)).isoformat(),
        "delivery_location": "تهران",
        "delivery_terms": "تحویل درب انبار",
        "tax_included": False,
        "provenance": "Manual offer #1",
    }
    assert list(MockPriceProvider([data]).observations())[0].amount.as_tuple().exponent == -6
    row = create(client, tokens[0], "price-observations", data)
    assert row["amount"] == "123456.123456" and row["status"] == "pending"
    path = "/api/v1/price-observations/" + row["id"]
    assert (
        client.post(path + "/decision", headers=tokens[0], json={"status": "approved"}).status_code
        == 422
    )
    source_data = {k: source[k] for k in ("code", "name", "kind", "provenance")}
    assert (
        client.put(
            "/api/v1/price-sources/" + source["id"],
            headers=tokens[0],
            json={**source_data, "approved": True},
        ).status_code
        == 200
    )
    assert (
        client.post(path + "/decision", headers=tokens[2], json={"status": "approved"}).status_code
        == 403
    )
    assert (
        client.post(path + "/decision", headers=tokens[0], json={"status": "approved"}).status_code
        == 200
    )
    assert (
        client.get("/api/v1/price-observations?approved_only=true", headers=tokens[0]).json()[
            "total"
        ]
        == 1
    )
    assert client.put(path, headers=tokens[0], json=data).status_code == 405
    assert client.delete(path, headers=tokens[0]).status_code == 405
    create(client, tokens[0], "price-observations", {**data, "amount": 12.3}, expected=422)
    expired = create(
        client,
        tokens[0],
        "price-observations",
        {
            **data,
            "observed_at": (now - timedelta(days=2)).isoformat(),
            "valid_until": (now - timedelta(days=1)).isoformat(),
        },
    )
    assert (
        client.post(
            "/api/v1/price-observations/" + expired["id"] + "/decision",
            headers=tokens[0],
            json={"status": "approved"},
        ).status_code
        == 422
    )
    create(client, tokens[1], "price-observations", data, expected=404)


def test_readiness_openapi_and_errors(world):
    client, tokens, _, _ = world
    assert client.get("/api/v1/ready").status_code == 200
    api = client.get("/openapi.json").json()
    assert "ProductInput" in api["components"]["schemas"]
    assert client.get("/api/v1/products?sort=password_hash", headers=tokens[0]).status_code == 422
    assert client.get("/api/v1/products/" + str(uuid.uuid4()), headers=tokens[0]).status_code == 404
    with engine().begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num='old'"))
    try:
        assert client.get("/api/v1/ready").status_code == 503
    finally:
        with engine().begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num='0001_m1'"))
