from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from app import models as m
from app.db import engine
from conftest import create
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture
def follow_up(world):
    client, tokens, *_ = world
    party = create(
        client,
        tokens[0],
        "parties",
        {"name": "Follow party", "kind": "legal_entity", "roles": ["customer", "supplier"]},
    )
    payload = {
        "party_id": party["id"],
        "name": "Follow%_literal",
        "kind": "call",
        "due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "notes": "Initial note",
    }
    item = create(client, tokens[0], "crm-follow-ups", payload, key="follow-up")
    return party, payload, item


def test_follow_up_crud_replay_scope_permissions_and_labels(world, follow_up):
    client, tokens, *_ = world
    party, payload, item = follow_up
    assert create(client, tokens[0], "crm-follow-ups", payload, key="follow-up")["id"] == item["id"]
    assert create(
        client,
        tokens[0],
        "crm-follow-ups",
        {**payload, "name": "different"},
        key="follow-up",
        expected=409,
    )
    assert create(client, tokens[2], "crm-follow-ups", payload, expected=403)
    path = "/api/v1/crm-follow-ups/" + item["id"]
    assert client.get(path, headers=tokens[1]).status_code == 404
    assert client.put(path, headers=tokens[1], json=payload).status_code == 404
    assert client.get("/api/v1/crm-follow-ups", headers=tokens[1]).json()["total"] == 0
    page = client.get(
        "/api/v1/crm-follow-ups", headers=tokens[2], params={"q": "%_", "party_id": party["id"]}
    ).json()
    assert page["total"] == 1 and page["items"][0]["display_names"]["party_id"] == party["name"]
    assert (
        client.put(path, headers=tokens[0], json={**payload, "status": "completed"}).status_code
        == 200
    )
    assert client.delete("/api/v1/parties/" + party["id"], headers=tokens[0]).status_code == 409
    assert client.delete(path, headers=tokens[2]).status_code == 403
    assert client.delete(path, headers=tokens[0]).status_code == 200
    with Session(engine()) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(m.AuditEvent.resource == "crm-follow-ups")
            )
            == 3
        )
        for model in (m.PriceObservation, m.StockEntry, m.SalesDraft):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_follow_up_overdue_filter_counts_pages_status_and_timezone(world, follow_up):
    client, tokens, *_ = world
    _, payload, item = follow_up
    future = create(
        client,
        tokens[0],
        "crm-follow-ups",
        {**payload, "name": "Future", "due_at": "2099-01-01T12:00:00+03:30"},
    )
    done = create(
        client, tokens[0], "crm-follow-ups", {**payload, "name": "Done", "status": "completed"}
    )
    response = client.get(
        "/api/v1/crm-follow-ups",
        headers=tokens[0],
        params={"overdue_only": "true", "limit": 1, "sort": "due_at"},
    )
    assert response.status_code == 200 and response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == item["id"]
    assert (
        client.get(
            "/api/v1/crm-follow-ups",
            headers=tokens[0],
            params={"overdue_only": "true", "status": "completed"},
        ).json()["total"]
        == 0
    )
    assert (
        client.get("/api/v1/crm-follow-ups?offset=1&limit=1", headers=tokens[0]).json()["total"]
        == 3
    )
    assert (
        client.get("/api/v1/crm-follow-ups/" + future["id"], headers=tokens[0])
        .json()["due_at"]
        .startswith("2099-01-01T08:30:00")
    )
    assert client.get("/api/v1/products?overdue_only=true", headers=tokens[0]).status_code == 422
    assert (
        client.get("/api/v1/crm-follow-ups?status=completed", headers=tokens[0]).json()["items"][0][
            "id"
        ]
        == done["id"]
    )


def test_follow_up_foreign_keys_invalid_inputs_and_inactive_party(world, follow_up):
    client, tokens, orgs, *_ = world
    party, payload, item = follow_up
    create(client, tokens[1], "crm-follow-ups", payload, expected=404)
    for override in (
        {"due_at": "2026-10-25T12:00:00"},
        {"kind": "send_message"},
        {"status": "approved"},
        {"organization_id": orgs[1]},
    ):
        create(client, tokens[0], "crm-follow-ups", {**payload, **override}, expected=422)
    assert (
        client.put(
            "/api/v1/parties/" + party["id"],
            headers=tokens[0],
            json={
                "name": party["name"],
                "kind": "legal_entity",
                "roles": ["customer", "supplier"],
                "active": False,
            },
        ).status_code
        == 200
    )
    create(client, tokens[0], "crm-follow-ups", {**payload, "name": "New"}, expected=409)
    assert (
        client.put(
            "/api/v1/crm-follow-ups/" + item["id"],
            headers=tokens[0],
            json={**payload, "status": "cancelled"},
        ).status_code
        == 200
    )
    with Session(engine()) as db:
        db.add(
            m.FollowUp(
                organization_id=UUID(orgs[1]),
                party_id=UUID(party["id"]),
                name="Foreign",
                kind="call",
                due_at=datetime.now(UTC),
                status="open",
                notes="",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


@pytest.mark.parametrize("due_at", ["0001-01-01T00:00:00+03:30", "9999-12-31T23:59:59-03:30"])
def test_follow_up_utc_overflow_is_validation_error_without_writes(world, follow_up, due_at):
    client, tokens, *_ = world
    _, payload, _ = follow_up
    with Session(engine()) as db:
        before = tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (m.FollowUp, m.AuditEvent, m.IdempotencyRecord)
        )
    create(
        client,
        tokens[0],
        "crm-follow-ups",
        {**payload, "due_at": due_at},
        key="utc-overflow",
        expected=422,
    )
    with Session(engine()) as db:
        after = tuple(
            db.scalar(select(func.count()).select_from(model))
            for model in (m.FollowUp, m.AuditEvent, m.IdempotencyRecord)
        )
    assert after == before
    create(client, tokens[0], "crm-follow-ups", payload, key="utc-overflow")
