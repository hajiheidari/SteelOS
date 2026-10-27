import json

from conftest import create


def identifier(client, headers, product, kind, value):
    return create(
        client,
        headers,
        "product-identifiers",
        {"product_id": product["id"], "kind": kind, "value": value},
    )


def test_product_identifier_search_preserves_literal_matching_scope_count_and_filters(
    world, catalog
):
    client, tokens, *_ = world
    category, payload, product = catalog
    other = create(
        client,
        tokens[0],
        "products",
        {
            **payload,
            "sku": "other-3",
            "name": "Other",
            "attributes": {"thickness": {"value": "3", "unit": "mm"}},
        },
    )
    foreign_category = create(
        client,
        tokens[1],
        "catalog-references",
        {
            "kind": "category",
            "code": "foreign",
            "name": "Other",
            "attribute_rules": {"thickness": {"unit": "mm", "required": True}},
        },
    )
    foreign = create(
        client, tokens[1], "products", {**payload, "category_id": foreign_category["id"]}
    )
    term = "Ref%_\\2026"
    identifier(client, tokens[0], product, "barcode", term)
    identifier(client, tokens[0], product, "vendor", term)
    identifier(client, tokens[0], other, "barcode", "RefZZ2026")
    identifier(client, tokens[1], foreign, "barcode", term)
    response = client.get(
        "/api/v1/products", headers=tokens[2], params={"q": term.lower(), "limit": 1}
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == product["id"]
    # Two matching aliases must not duplicate a product or inflate pagination totals.
    first = client.get(
        "/api/v1/products",
        headers=tokens[0],
        params={"q": "ref", "limit": 1, "sort": "sku", "direction": "asc"},
    ).json()
    second = client.get(
        "/api/v1/products",
        headers=tokens[0],
        params={"q": "ref", "limit": 1, "offset": 1, "sort": "sku", "direction": "asc"},
    ).json()
    assert first["total"] == second["total"] == 2
    assert {first["items"][0]["id"], second["items"][0]["id"]} == {product["id"], other["id"]}
    filtered = client.get(
        "/api/v1/products",
        headers=tokens[0],
        params={"q": "ref", "attributes": json.dumps({"thickness": {"value": "2", "unit": "mm"}})},
    ).json()
    assert filtered["total"] == 1 and filtered["items"][0]["id"] == product["id"]
    assert (
        client.get(
            "/api/v1/products", headers=tokens[0], params={"q": term, "active": "false"}
        ).json()["total"]
        == 0
    )
    scoped = client.get("/api/v1/products", headers=tokens[1], params={"q": term}).json()
    assert scoped["total"] == 1 and scoped["items"][0]["id"] == foreign["id"]
    assert (
        client.get("/api/v1/products", headers=tokens[0], params={"q": product["sku"]}).json()[
            "total"
        ]
        == 1
    )


def test_identifier_list_search_filters_value_and_reflects_rename_delete(world, catalog):
    client, tokens, *_ = world
    _, _, product = catalog
    term = "Unique%_\\Identifier"
    first = identifier(client, tokens[0], product, "barcode", term)
    identifier(client, tokens[0], product, "vendor", "unrelated")
    response = client.get(
        "/api/v1/product-identifiers", headers=tokens[2], params={"q": term.lower()}
    )
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == first["id"]
    assert (
        client.get("/api/v1/product-identifiers", headers=tokens[1], params={"q": term}).json()[
            "total"
        ]
        == 0
    )
    update = client.put(
        "/api/v1/product-identifiers/" + first["id"],
        headers=tokens[0],
        json={"product_id": product["id"], "kind": "barcode", "value": "Renamed-code"},
    )
    assert update.status_code == 200
    assert (
        client.get("/api/v1/products", headers=tokens[0], params={"q": term}).json()["total"] == 0
    )
    assert (
        client.get("/api/v1/products", headers=tokens[0], params={"q": "renamed-code"}).json()[
            "total"
        ]
        == 1
    )
    assert (
        client.delete("/api/v1/product-identifiers/" + first["id"], headers=tokens[0]).status_code
        == 200
    )
    assert (
        client.get("/api/v1/products", headers=tokens[0], params={"q": "renamed-code"}).json()[
            "total"
        ]
        == 0
    )


def test_identifier_kind_length_is_validated_before_database_write(world, catalog):
    from uuid import UUID

    from app.db import engine
    from app.models import AuditEvent, IdempotencyRecord
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    client, tokens, orgs, _ = world
    _, _, product = catalog
    longest = "k" * 30
    existing = identifier(client, tokens[0], product, longest, "boundary-code")
    for size in (31, 80):
        payload = {"product_id": product["id"], "kind": "k" * size, "value": "invalid-kind"}
        key = f"invalid-kind-{size}"
        result = client.post(
            "/api/v1/product-identifiers",
            headers={**tokens[0], "Idempotency-Key": key},
            json=payload,
        )
        assert result.status_code == 422, result.status_code
        assert result.json()["error"]["code"] == "validation_error"
        update = client.put(
            "/api/v1/product-identifiers/" + existing["id"], headers=tokens[0], json=payload
        )
        assert update.status_code == 422
        with Session(engine()) as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(IdempotencyRecord)
                    .where(
                        IdempotencyRecord.organization_id == UUID(orgs[0]),
                        IdempotencyRecord.key == key,
                    )
                )
                == 0
            )
    persisted = client.get(
        "/api/v1/product-identifiers/" + existing["id"], headers=tokens[0]
    ).json()
    assert persisted["kind"] == longest and persisted["value"] == "boundary-code"
    assert client.get("/api/v1/product-identifiers", headers=tokens[0]).json()["total"] == 1
    with Session(engine()) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.organization_id == UUID(orgs[0]),
                    AuditEvent.resource == "product-identifiers",
                )
            )
            == 1
        )
    create(
        client,
        tokens[0],
        "product-identifiers",
        {"product_id": product["id"], "kind": "vendor", "value": "corrected-kind"},
        key="invalid-kind-31",
    )


def test_product_search_combines_name_sku_and_alias_without_duplicates(world, catalog):
    client, tokens, *_ = world
    _, payload, product = catalog
    update = client.put(
        "/api/v1/products/" + product["id"],
        headers=tokens[0],
        json={**payload, "name": "Combined-needle name"},
    )
    assert update.status_code == 200
    identifier(client, tokens[0], product, "barcode", "Combined-needle alias")
    second = create(
        client,
        tokens[0],
        "products",
        {
            **payload,
            "sku": "COMBINED-NEEDLE-SKU",
            "name": "Second",
            "attributes": {"thickness": {"value": "3", "unit": "mm"}},
        },
    )
    third = create(
        client,
        tokens[0],
        "products",
        {
            **payload,
            "sku": "third",
            "name": "Third",
            "attributes": {"thickness": {"value": "4", "unit": "mm"}},
        },
    )
    identifier(client, tokens[0], third, "barcode", "Combined-needle third")
    identifier(client, tokens[0], third, "vendor", "Combined-needle third")
    ids = []
    for offset in range(3):
        response = client.get(
            "/api/v1/products",
            headers=tokens[2],
            params={
                "q": "combined-needle",
                "sort": "sku",
                "direction": "asc",
                "offset": offset,
                "limit": 1,
            },
        )
        assert response.status_code == 200
        assert response.json()["total"] == 3
        ids.append(response.json()["items"][0]["id"])
    assert len(set(ids)) == 3 and set(ids) == {product["id"], second["id"], third["id"]}
    filtered = client.get(
        "/api/v1/products",
        headers=tokens[2],
        params={
            "q": "combined-needle",
            "attributes": json.dumps(
                {
                    "thickness": {
                        "min": {"value": "2", "unit": "mm"},
                        "max": {"value": "3", "unit": "mm"},
                    }
                }
            ),
        },
    ).json()
    assert filtered["total"] == 2
    assert {row["id"] for row in filtered["items"]} == {product["id"], second["id"]}
    assert (
        client.get("/api/v1/products", headers=tokens[1], params={"q": "combined-needle"}).json()[
            "total"
        ]
        == 0
    )
