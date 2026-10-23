"""Validate catalog invariants across separate PostgreSQL transactions."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep

from app.db import engine
from app.models import Product
from app.modules import resources
from conftest import create
from sqlalchemy import text


def test_category_rules_cannot_change_during_validated_product_creation(world, monkeypatch):
    client, tokens, _, _ = world
    category = create(
        client,
        tokens[0],
        "catalog-references",
        {
            "kind": "category",
            "code": "concurrent-sheet",
            "name": "ورق",
            "attribute_rules": {"thickness": {"unit": "mm", "required": True}},
        },
    )
    product = {
        "sku": "RACE",
        "name": "ورق آزمایشی",
        "category_id": category["id"],
        "unit": "kg",
        "attributes": {"thickness": {"value": "2", "unit": "mm"}},
    }
    validated, release = Event(), Event()
    original = resources.validate_domain

    def pause_after_validation(db, ctx, model, data, current=None):
        result = original(db, ctx, model, data, current)
        if model is Product:
            validated.set()
            assert release.wait(timeout=10), "Test failed to release product transaction"
        return result

    monkeypatch.setattr(resources, "validate_domain", pause_after_validation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        creation = pool.submit(create, client, tokens[0], "products", product)
        try:
            assert validated.wait(timeout=5)
            update = pool.submit(
                client.put,
                "/api/v1/catalog-references/" + category["id"],
                headers=tokens[0],
                json={
                    "kind": "category",
                    "code": "concurrent-sheet",
                    "name": "ورق",
                    "attribute_rules": {"thickness": {"unit": "cm", "required": True}},
                },
            )
            # Wait until the second transaction either finishes (old bug) or waits
            # on the actual catalog row lock. No fixed race-ordering sleep.
            deadline = monotonic() + 5
            observed = False
            with engine().connect() as connection:
                while monotonic() < deadline:
                    connection.commit()  # Refresh PostgreSQL activity snapshot.
                    waiting = connection.scalar(
                        text("""
                        SELECT EXISTS (SELECT 1 FROM pg_stat_activity
                        WHERE datname = current_database() AND wait_event_type = 'Lock'
                          AND query LIKE '%catalog_references%')
                    """)
                    )
                    if update.done() or waiting:
                        observed = True
                        break
                    sleep(0.01)
            assert observed, "Category update did not execute within the test deadline"
        finally:
            release.set()
        created = creation.result(timeout=5)
        response = update.result(timeout=5)
    assert response.status_code == 409, response.text
    stored = client.get("/api/v1/products/" + created["id"], headers=tokens[0]).json()
    rules = client.get("/api/v1/catalog-references/" + category["id"], headers=tokens[0]).json()
    assert (
        stored["attributes"]["thickness"]["unit"] == rules["attribute_rules"]["thickness"]["unit"]
    )
