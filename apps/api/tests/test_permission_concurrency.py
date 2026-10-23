"""Queued writes must recheck authority after their transaction lock is granted."""

from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from uuid import UUID

import pytest
from app.db import engine
from app.models import AuthSession, Membership
from conftest import create
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session


@pytest.mark.parametrize(
    "operation", ["create", "replay", "update", "delete", "admin_definition", "removed_member"]
)
def test_queued_creation_rechecks_current_membership(world, operation):
    client, tokens, orgs, users = world
    initial_role = "admin" if operation in ("admin_definition", "delete") else "editor"
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2],
            headers=tokens[0],
            json={"role": initial_role},
        ).status_code
        == 200
    )
    resource = "catalog-references" if operation == "admin_definition" else "parties"
    payload = (
        {"kind": "category", "code": "queued", "name": "Queued definition"}
        if operation == "admin_definition"
        else {"name": "Queued party", "kind": "individual", "roles": ["customer"]}
    )
    headers = {**tokens[2], "Idempotency-Key": "queued-write"}
    existing = None
    if operation in ("replay", "update", "delete"):
        existing = create(client, tokens[2], resource, payload, key="queued-write")
    with Session(engine()) as gate, ThreadPoolExecutor(max_workers=1) as pool:
        membership = gate.scalar(
            select(Membership)
            .where(
                Membership.organization_id == UUID(orgs[0]), Membership.user_id == UUID(users[2])
            )
            .with_for_update()
        )
        if operation == "delete":
            write = pool.submit(client.delete, "/api/v1/parties/" + existing["id"], headers=headers)
        elif operation == "update":
            write = pool.submit(
                client.put,
                "/api/v1/parties/" + existing["id"],
                headers=headers,
                json={**payload, "name": "Unauthorized edit"},
            )
        else:
            write = pool.submit(client.post, "/api/v1/" + resource, headers=headers, json=payload)
        try:
            deadline = monotonic() + 5
            waiting = False
            with engine().connect() as monitor:
                while monotonic() < deadline:
                    monitor.commit()
                    waiting = monitor.scalar(
                        text("""
                        SELECT EXISTS(SELECT 1 FROM pg_stat_activity
                        WHERE datname=current_database() AND wait_event_type='Lock'
                          AND query LIKE '%memberships%')
                    """)
                    )
                    if waiting or write.done():
                        break
                    sleep(0.01)
            assert waiting, "Write did not reach the membership lock"
            if operation == "removed_member":
                gate.execute(delete(AuthSession).where(AuthSession.user_id == UUID(users[2])))
                gate.delete(membership)
            else:
                membership.role = "editor" if operation == "admin_definition" else "viewer"
            gate.commit()
        finally:
            gate.rollback()  # Always release the blocked request if a test assertion fails.
        result = write.result(timeout=5)
    assert result.status_code == (401 if operation == "removed_member" else 403), result.text
    total = client.get("/api/v1/" + resource, headers=tokens[0]).json()["total"]
    assert total == (1 if existing else 0)
    if existing:
        persisted = client.get("/api/v1/parties/" + existing["id"], headers=tokens[0]).json()
        assert persisted["name"] == payload["name"]
