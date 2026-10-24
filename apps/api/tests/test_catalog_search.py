import json

from conftest import create


def test_exact_attribute_search_is_extensible_scoped_and_converts_only_length_units(world):
    client, tokens, *_ = world
    rows = []
    for index, units, values in (
        (0, ("mm", "mm"), ("2", "1200")),
        (0, ("cm", "m"), ("0.2", "1.2")),
        (0, ("mm", "mm"), ("3", "1200")),
        (1, ("mm", "mm"), ("2", "1200")),
    ):
        stamp = str(len(rows))
        category = create(
            client,
            tokens[index],
            "catalog-references",
            {
                "kind": "category",
                "code": "dim-" + stamp,
                "name": "ورق " + stamp,
                "attribute_rules": {
                    "thickness": {"unit": units[0], "required": True},
                    "width": {"unit": units[1], "required": True},
                    "custom_measure": {"unit": "none", "required": False},
                },
            },
        )
        rows.append(
            create(
                client,
                tokens[index],
                "products",
                {
                    "sku": "DIM-" + stamp,
                    "name": "ورق " + stamp,
                    "category_id": category["id"],
                    "unit": "kg",
                    "attributes": {
                        "thickness": {"value": values[0], "unit": units[0]},
                        "width": {"value": values[1], "unit": units[1]},
                        "custom_measure": {"value": "3", "unit": "none"},
                    },
                },
            )
        )
    interval = {
        "thickness": {"min": {"value": "0.2", "unit": "cm"}, "max": {"value": "3", "unit": "mm"}}
    }
    ranged = client.get(
        "/api/v1/products",
        headers=tokens[2],
        params={"attributes": json.dumps(interval), "limit": 1},
    ).json()
    assert ranged["total"] == 3 and len(ranged["items"]) == 1
    foreign = client.get(
        "/api/v1/products", headers=tokens[1], params={"attributes": json.dumps(interval)}
    ).json()
    assert foreign["total"] == 1 and foreign["items"][0]["id"] == rows[3]["id"]
    # Missing or corrupted legacy JSON must not cause a PostgreSQL numeric cast failure.
    from app.db import engine
    from app.models import Product
    from sqlalchemy import update

    for raw in (
        {"value": "not-numeric", "unit": "mm"},
        {"value": "1e999999", "unit": "mm"},
        {"value": ["2"], "unit": "mm"},
        {"value": "9" * 100, "unit": "mm"},
        {"value": 2, "unit": "mm"},
        {"value": None, "unit": "mm"},
        {"value": "0", "unit": "mm"},
        {"value": "-2", "unit": "mm"},
        {},
    ):
        with engine().begin() as conn:
            conn.execute(
                update(Product)
                .where(Product.id == rows[2]["id"])
                .values(attributes={"thickness": raw})
            )
        safe = client.get(
            "/api/v1/products", headers=tokens[0], params={"attributes": json.dumps(interval)}
        )
        assert safe.status_code == 200 and safe.json()["total"] == 2
        safe_comparison = client.get(
            "/api/v1/products",
            headers=tokens[0],
            params={
                "attributes": json.dumps(
                    {"thickness": {"op": "lt", "bound": {"value": "3", "unit": "mm"}}}
                )
            },
        )
        assert safe_comparison.status_code == 200 and safe_comparison.json()["total"] == 2

    with engine().begin() as conn:
        conn.execute(
            update(Product)
            .where(Product.id == rows[2]["id"])
            .values(
                attributes={
                    "thickness": {"value": "3", "unit": "mm"},
                    "width": {"value": "1200", "unit": "mm"},
                    "custom_measure": {"value": "3", "unit": "none"},
                }
            )
        )
    for lo, hi, expected in (("2.000001", "2.999999", 0), ("2", "2", 2), ("3", "3", 1)):
        bound = {
            "thickness": {"min": {"value": lo, "unit": "mm"}, "max": {"value": hi, "unit": "mm"}}
        }
        result = client.get(
            "/api/v1/products", headers=tokens[0], params={"attributes": json.dumps(bound)}
        )
        assert result.status_code == 200 and result.json()["total"] == expected
    for key, lo, hi, unit, expected in (
        ("custom_measure", "2", "3", "none", 3),
        ("custom_measure", "2", "3", "kg", 0),
        ("thickness", "2", "3", "kg", 0),
        ("missing", "1", "4", "mm", 0),
        ("thickness", "0.000001", "0.000002", "m", 0),
        ("thickness", "99999999999999", "99999999999999.999999", "m", 0),
    ):
        response = client.get(
            "/api/v1/products",
            headers=tokens[0],
            params={
                "attributes": json.dumps(
                    {key: {"min": {"value": lo, "unit": unit}, "max": {"value": hi, "unit": unit}}}
                )
            },
        )
        assert response.status_code == 200 and response.json()["total"] == expected
    for op, expected in (("gt", 1), ("gte", 3), ("lt", 0), ("lte", 2)):
        raw = {"thickness": {"op": op, "bound": {"value": "0.2", "unit": "cm"}}}
        response = client.get(
            "/api/v1/products", headers=tokens[2], params={"attributes": json.dumps(raw)}
        )
        assert response.status_code == 200 and response.json()["total"] == expected
        assert all(
            row["id"] in {product["id"] for product in rows[:3]} for row in response.json()["items"]
        )
        other = client.get(
            "/api/v1/products", headers=tokens[1], params={"attributes": json.dumps(raw)}
        )
        assert other.json()["total"] == (1 if op in ("gte", "lte") else 0)
    for key, op, value, unit, expected in (
        ("width", "gte", "1200", "mm", 3),
        ("width", "gt", "1.2", "m", 0),
        ("custom_measure", "gte", "3", "none", 3),
        ("custom_measure", "gte", "3", "kg", 0),
    ):
        result = client.get(
            "/api/v1/products",
            headers=tokens[0],
            params={
                "attributes": json.dumps(
                    {key: {"op": op, "bound": {"value": value, "unit": unit}}}
                ),
                "limit": 1,
            },
        )
        assert result.status_code == 200 and result.json()["total"] == expected
        assert len(result.json()["items"]) == min(1, expected)
    filters = {
        "thickness": {"value": "۲٫۰۰۰۰۰۰", "unit": "mm"},
        "width": {"value": "۱٬۲۰۰", "unit": "mm"},
        "custom_measure": {"value": "3.000000", "unit": "none"},
    }
    params = {"attributes": json.dumps(filters), "q": "ورق", "limit": 1}
    response = client.get("/api/v1/products", headers=tokens[2], params=params)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2 and len(response.json()["items"]) == 1
    second = client.get(
        "/api/v1/products", headers=tokens[0], params={**params, "offset": 1}
    ).json()
    assert {response.json()["items"][0]["id"], second["items"][0]["id"]} == {
        rows[0]["id"],
        rows[1]["id"],
    }
    other = client.get("/api/v1/products", headers=tokens[1], params=params).json()
    assert other["total"] == 1 and other["items"][0]["id"] == rows[3]["id"]
    for key, dimension in (
        ("width", {"value": "1200", "unit": "kg"}),
        ("custom_measure", {"value": "3", "unit": "kg"}),
        ("missing", {"value": "2", "unit": "mm"}),
        ("thickness", {"value": "2.000001", "unit": "mm"}),
    ):
        result = client.get(
            "/api/v1/products",
            headers=tokens[0],
            params={"attributes": json.dumps({key: dimension})},
        )
        assert result.status_code == 200 and result.json()["total"] == 0
    assert (
        client.get(
            "/api/v1/products",
            headers=tokens[0],
            params={"q": "not-present", **{"attributes": json.dumps(filters)}},
        ).json()["total"]
        == 0
    )


INVALID_FILTERS = [
    json.dumps(
        {"width": {"min": {"value": "3", "unit": "mm"}, "max": {"value": "2", "unit": "mm"}}}
    ),
    json.dumps(
        {"width": {"min": {"value": "2", "unit": "kg"}, "max": {"value": "3", "unit": "mm"}}}
    ),
    json.dumps({"width": {"min": {"value": "2", "unit": "mm"}}}),
    json.dumps({"width": {"op": "eq", "bound": {"value": "2", "unit": "mm"}}}),
    json.dumps({"width": {"op": "gt", "bound": {"value": True, "unit": "mm"}}}),
    json.dumps({"width": {"op": "gt", "bound": {"value": 2.5, "unit": "mm"}}}),
    json.dumps(
        {
            "width": {
                "op": "gt",
                "bound": {"value": "2", "unit": "mm"},
                "min": {"value": "1", "unit": "mm"},
            }
        }
    ),
    "{",
    "[]",
    "null",
    '["width"]',
    '{"width":{"value":"2","unit":"mm"},"width":{"value":"3","unit":"mm"}}',
    '{"width":{"value":"2","unit":"mm","unit":"m"}}',
    json.dumps({"width": {"value": True, "unit": "mm"}}),
    json.dumps({"width": {"value": 1.2, "unit": "mm"}}),
    json.dumps({"width": {"value": "NaN", "unit": "mm"}}),
    json.dumps({"width": {"value": "1E999999999", "unit": "mm"}}),
    json.dumps({"width": {"value": "۲٬۵", "unit": "mm"}}),
    json.dumps({"width": {"value": "0.0000001", "unit": "mm"}}),
    json.dumps({"width": {"value": "2", "unit": "inch"}}),
    json.dumps({"width": {"value": "-2", "unit": "mm"}}),
    json.dumps({"width": {"value": "2", "unit": "mm", "organization_id": "foreign"}}),
    json.dumps({"x' OR TRUE --": {"value": "2", "unit": "mm"}}),
    json.dumps({str(index): {"value": "2", "unit": "mm"} for index in range(9)}),
    "[" * 1100 + "]" * 1100,
    " " * 4097,
]


def test_invalid_attribute_filters_return_structured_422(world):
    client, tokens, *_ = world
    for raw in INVALID_FILTERS:
        response = client.get("/api/v1/products", headers=tokens[0], params={"attributes": raw})
        assert response.status_code == 422, response.text
        assert "error" in response.json()


def test_attribute_filter_is_not_silently_accepted_on_other_resources(world):
    client, tokens, *_ = world
    response = client.get("/api/v1/parties", headers=tokens[0], params={"attributes": "{}"})
    assert response.status_code == 422
