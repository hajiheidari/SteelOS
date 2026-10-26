"""Reject unstoreable text before DB writes while preserving valid Persian Unicode."""

import copy
import json
from uuid import uuid4

import pytest
from app import models as m
from app.db import engine
from app.modules.inventory.schemas import DraftInput as InventoryDraft
from app.modules.sales.schemas import DraftInput as SalesDraft
from app.modules.sales.schemas import ReviewInput
from app.schemas import Login, PasswordUpdate
from conftest import create
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

VALID = "متن‌ فارسی 😀\nمعتبر"


def counts():
    with Session(engine()) as db:
        return tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (
                m.Product,
                m.Party,
                m.Warehouse,
                m.PriceSource,
                m.FollowUp,
                m.AuditEvent,
                m.IdempotencyRecord,
            )
        )


def set_value(payload, path, value):
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def json_request(client, method, path, token, payload):
    # An isolated surrogate is legal JSON escape syntax but not valid UTF-8 text.
    return getattr(client, method)(
        path,
        headers={**token, "Content-Type": "application/json", "Idempotency-Key": "text-validation"},
        content=json.dumps(payload, ensure_ascii=True).encode("ascii"),
    )


@pytest.mark.parametrize("invalid", ["Private\x00value", "Private\ud800value"])
@pytest.mark.parametrize(
    "resource,path",
    [
        ("products", ("name",)),
        ("parties", ("name",)),
        ("parties", ("contacts", 0, "value")),
        ("warehouses", ("address",)),
        ("price-sources", ("provenance",)),
        ("crm-follow-ups", ("notes",)),
    ],
)
def test_stored_text_create_update_rejects_without_writes(world, catalog, resource, path, invalid):
    client, tokens, *_ = world
    if resource == "products":
        payload = {
            **catalog[1],
            "sku": "TEXT",
            "attributes": {"thickness": {"value": "9", "unit": "mm"}},
        }
    elif resource == "parties":
        payload = {
            "name": "Text party",
            "kind": "individual",
            "roles": ["customer"],
            "contacts": [{"name": "Contact", "kind": "contact_person", "value": "Valid"}],
        }
    elif resource == "warehouses":
        payload = {"name": "Text warehouse", "code": "TEXT", "city": "تهران", "address": "Valid"}
    elif resource == "price-sources":
        payload = {"name": "Text source", "code": "TEXT", "kind": "manual", "provenance": "Valid"}
    else:
        party = create(
            client,
            tokens[0],
            "parties",
            {"name": "Text party", "kind": "individual", "roles": ["customer"]},
        )
        payload = {
            "name": "Text follow-up",
            "party_id": party["id"],
            "due_at": "2099-01-01T00:00:00Z",
            "notes": "Valid",
        }
    set_value(payload, path, VALID)
    bad = copy.deepcopy(payload)
    set_value(bad, path, invalid)
    before = counts()
    result = json_request(client, "post", "/api/v1/" + resource, tokens[0], bad)
    assert result.status_code == 422 and "Private" not in result.text
    assert counts() == before
    valid = json_request(client, "post", "/api/v1/" + resource, tokens[0], payload)
    assert valid.status_code == 201, valid.text
    record = valid.json()
    selected = record
    for key in path:
        selected = selected[key]
    assert selected == VALID
    before = counts()
    record_path = "/api/v1/" + resource + "/" + record["id"]
    result = json_request(client, "put", record_path, tokens[0], bad)
    assert result.status_code == 422 and "Private" not in result.text
    assert counts() == before
    assert client.get(record_path, headers=tokens[0]).json() == record


@pytest.mark.parametrize(
    "schema,payload",
    [
        (
            InventoryDraft,
            {
                "lot_id": uuid4(),
                "kind": "receipt",
                "quantity": "1",
                "to_location_id": uuid4(),
                "reference": "Valid",
            },
        ),
        (
            SalesDraft,
            {
                "code": "TEXT",
                "customer_id": uuid4(),
                "currency": "IRR",
                "lines": [{"price_id": uuid4(), "quantity": "1"}],
            },
        ),
        (ReviewInput, {"expected_version": 1, "decision": "accepted"}),
    ],
)
@pytest.mark.parametrize("invalid", ["Private\x00value", "Private\udfffvalue"])
def test_transaction_notes_reject_unstoreable_text(schema, payload, invalid):
    with pytest.raises(ValidationError) as error:
        schema.model_validate({**payload, "note": invalid})
    assert error.value.errors()[0]["loc"] == ("note",)
    assert schema.model_validate({**payload, "note": VALID}).note == VALID


def test_password_unicode_preserves_whitespace_and_nul_but_rejects_surrogates():
    password = "  Persian‌ 😀\x00secret  "
    assert (
        Login(email="user@example.test", password=password, organization_id=uuid4()).password
        == password
    )
    assert PasswordUpdate(current_password=password, new_password=password).new_password == password
    with pytest.raises(ValidationError):
        Login(email="user@example.test", password="Private\ud800value", organization_id=uuid4())


def test_invalid_login_unicode_rejected_before_password_verification(world, monkeypatch):
    from app.security import hasher

    client, tokens, orgs, *_ = world

    def unexpected(*args, **kwargs):
        pytest.fail("Invalid Unicode must not reach password verification")

    monkeypatch.setattr(type(hasher), "verify", unexpected)
    before = counts()
    result = json_request(
        client,
        "post",
        "/api/v1/auth/login",
        tokens[0],
        {
            "email": "user0@example.test",
            "password": "Private\ud800value",
            "organization_id": orgs[0],
        },
    )
    assert result.status_code == 422 and "Private" not in result.text
    assert counts() == before


@pytest.mark.parametrize(
    "endpoint,parameter",
    [
        ("products", "q"),
        ("parties", "q"),
        ("warehouses", "q"),
        ("crm-follow-ups", "q"),
        ("inventory/lots", "q"),
        ("inventory/drafts", "q"),
        ("inventory/entries", "q"),
        ("inventory/reservations", "q"),
        ("sales-drafts", "q"),
        ("organization/members", "q"),
        ("products", "unit"),
        ("parties", "kind"),
        ("price-observations", "status"),
        ("inventory/drafts", "status"),
    ],
)
def test_query_text_rejected_before_sql_binding(world, endpoint, parameter):
    from sqlalchemy import event

    client, tokens, *_ = world
    bound_invalid = []

    def observe(connection, cursor, statement, parameters, context, executemany):
        values = parameters.values() if isinstance(parameters, dict) else parameters
        if any(isinstance(value, str) and "\x00" in value for value in values):
            bound_invalid.append(statement)

    before = counts()
    event.listen(engine(), "before_cursor_execute", observe)
    try:
        result = client.get(
            "/api/v1/" + endpoint, headers=tokens[0], params={parameter: "Private\x00value"}
        )
        assert result.status_code == 422 and "Private" not in result.text
        assert not bound_invalid
        if parameter == "q" and endpoint not in ("inventory/entries", "inventory/reservations"):
            assert (
                client.get(
                    "/api/v1/" + endpoint, headers=tokens[0], params={"q": "فارسی%_😀"}
                ).status_code
                == 200
            )
    finally:
        event.remove(engine(), "before_cursor_execute", observe)
    assert counts() == before
