"""Opt-in synthetic PostgreSQL query benchmark; never runs as part of pytest."""

import argparse
import hashlib
import json
import math
import statistics
import time
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.db import engine
from app.models import Organization, Product, ProductIdentifier, Reference
from app.modules import catalog_search
from app.modules.resources import apply_text_search
from psycopg.types.json import Jsonb
from sqlalchemy import func, insert, select, text


def explain(connection, statement):
    compiled = statement.compile(dialect=connection.dialect)
    parameters = {
        key: Jsonb(value) if isinstance(value, dict) else value
        for key, value in compiled.params.items()
    }
    # SQL text is compiled solely from fixed SQLAlchemy expressions; all values remain bound.
    return connection.exec_driver_sql(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + str(compiled), parameters
    ).scalar_one()[0]


def benchmark(rows_per_org=5000, repeats=5, identifier_search=False):
    database = engine()
    if not database.url.database.endswith("_benchmark"):
        raise SystemExit("Use an isolated, migrated DATABASE_URL ending in _benchmark")
    if not 100 <= rows_per_org <= 50000 or not 3 <= repeats <= 20:
        raise SystemExit("rows-per-org must be100..50000; repeats must be3..20")
    report = {
        "scope": "Synthetic query-only single-client warm-cache benchmark; not an API/load SLO",
        "recorded_at": datetime.now(UTC).isoformat(),
        "rows_per_organization": rows_per_org,
        "organizations": 2,
        "repeats": repeats,
        "queries": [],
        "identifier_search": identifier_search,
    }
    with database.connect() as connection:
        if connection.scalar(select(func.count()).select_from(Organization)):
            raise SystemExit("Benchmark database must contain no organizations")
        connection.rollback()
        transaction = connection.begin()
        try:
            connection.execute(text("SET LOCAL statement_timeout = '15s'"))
            report["postgres_version"] = connection.scalar(text("SHOW server_version"))
            organizations = [uuid.uuid4(), uuid.uuid4()]
            metadata = []
            for organization in organizations:
                categories = {unit: uuid.uuid4() for unit in catalog_search.LENGTH_FACTORS}
                connection.execute(
                    insert(Organization), {"id": organization, "name": "Synthetic benchmark"}
                )
                for unit, category in categories.items():
                    connection.execute(
                        insert(Reference),
                        {
                            "id": category,
                            "organization_id": organization,
                            "kind": "category",
                            "code": "synthetic-sheet-" + unit,
                            "name": "ورق مصنوعی " + unit,
                            "attribute_rules": {
                                "thickness": {"unit": unit, "required": True},
                                "length": {"unit": "mm", "required": True},
                            },
                        },
                    )
                rows = []
                for index in range(rows_per_org):
                    thickness = Decimal(index % 10 + 1)
                    unit = ("mm", "cm", "m")[index % 3]
                    stored = thickness * Decimal("0.001") / catalog_search.LENGTH_FACTORS[unit]
                    attributes = {
                        "thickness": {"value": format(stored.normalize(), "f"), "unit": unit},
                        "length": {"value": str(index + 1), "unit": "mm"},
                    }
                    active = index % 17 != 0
                    rows.append(
                        {
                            "id": uuid.uuid4(),
                            "organization_id": organization,
                            "category_id": categories[unit],
                            "sku": f"SYN-{index}",
                            "name": "ورق مصنوعی",
                            "unit": "kg",
                            "attributes": attributes,
                            "active": active,
                            "specification_hash": hashlib.sha256(
                                json.dumps(attributes, sort_keys=True).encode()
                            ).hexdigest(),
                        }
                    )
                    if organization == organizations[0]:
                        metadata.append((thickness, active))
                connection.execute(insert(Product), rows)
                if identifier_search:
                    connection.execute(
                        insert(ProductIdentifier),
                        [
                            {
                                "id": uuid.uuid4(),
                                "organization_id": organization,
                                "product_id": row["id"],
                                "kind": kind,
                                "value": f"REF%_\\{index}",
                            }
                            for index, row in enumerate(rows)
                            for kind in ("barcode", "vendor")
                        ],
                    )
            # Collect statistics only in the dedicated disposable database; seeded rows roll back.
            connection.execute(text("ANALYZE products"))
            if identifier_search:
                connection.execute(text("ANALYZE product_identifiers"))
            report["seeded_identifiers"] = connection.scalar(
                select(func.count()).select_from(ProductIdentifier)
            )
            report["seeded_products"] = connection.scalar(select(func.count()).select_from(Product))
            cases = (
                ("exact", {"thickness": {"value": "2", "unit": "mm"}}, lambda value: value == 2),
                (
                    "inclusive_mixed_units",
                    {
                        "thickness": {
                            "min": {"value": "0.2", "unit": "cm"},
                            "max": {"value": "3", "unit": "mm"},
                        }
                    },
                    lambda value: 2 <= value <= 3,
                ),
                (
                    "empty_interior",
                    {
                        "thickness": {
                            "min": {"value": "2.000001", "unit": "mm"},
                            "max": {"value": "2.999999", "unit": "mm"},
                        }
                    },
                    lambda value: False,
                ),
            )
            cases = [(name, raw, predicate, None) for name, raw, predicate in cases]
            if identifier_search:
                cases.extend(
                    [
                        ("text_name", {}, lambda value: True, "ورق"),
                        ("text_sku", {}, lambda value: True, "SYN-123"),
                        ("text_identifier_literal", {}, lambda value: True, "ref%_\\123"),
                        ("text_identifier_missing", {}, lambda value: True, "UNSEEN-ALIAS"),
                        ("text_identifier_range", cases[1][1], cases[1][2], "REF"),
                    ]
                )
            for name, raw, predicate, query in cases:
                filters = catalog_search.parse(json.dumps(raw))
                expected = sum(
                    active
                    and predicate(value)
                    and (
                        query is None
                        or any(
                            query.casefold() in candidate.casefold()
                            for candidate in ("ورق مصنوعی", f"SYN-{index}", f"REF%_\\{index}")
                        )
                    )
                    for index, (value, active) in enumerate(metadata)
                )
                scoped = catalog_search.apply(
                    select(Product).where(
                        Product.organization_id == organizations[0], Product.active.is_(True)
                    ),
                    Product,
                    filters,
                )
                if query is not None:
                    scoped = apply_text_search(scoped, Product, organizations[0], query)
                count = select(func.count()).select_from(scoped.subquery())
                page = scoped.order_by(Product.created_at.desc(), Product.id).limit(5)
                milliseconds = []
                for _ in range(repeats):
                    started = time.perf_counter()
                    total = connection.scalar(count)
                    records = connection.execute(page).mappings().all()
                    milliseconds.append((time.perf_counter() - started) * 1000)
                    assert total == expected, (name, total, expected)
                    assert len(records) == min(5, expected)
                    assert all(row["organization_id"] == organizations[0] for row in records)
                report["queries"].append(
                    {
                        "name": name,
                        "expected_count": expected,
                        "count_and_page_ms": {
                            "median": round(statistics.median(milliseconds), 3),
                            "p95": round(sorted(milliseconds)[math.ceil(repeats * 0.95) - 1], 3),
                        },
                        "count_plan": explain(connection, count),
                        "page_plan": explain(connection, page),
                    }
                )
        finally:
            transaction.rollback()
        report["rolled_back"] = (
            connection.scalar(select(func.count()).select_from(Organization)) == 0
            and connection.scalar(select(func.count()).select_from(Product)) == 0
            and connection.scalar(select(func.count()).select_from(ProductIdentifier)) == 0
        )
        assert report["rolled_back"]
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows-per-org", type=int, default=5000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identifier-search", action="store_true")
    arguments = parser.parse_args()
    result = benchmark(arguments.rows_per_org, arguments.repeats, arguments.identifier_search)
    arguments.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "seeded_products": result["seeded_products"],
                "queries": [
                    {"name": row["name"], **row["count_and_page_ms"]} for row in result["queries"]
                ],
                "rolled_back": result["rolled_back"],
            }
        )
    )
