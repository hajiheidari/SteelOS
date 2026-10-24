"""Session rotation must recheck state after waiting for transaction locks."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from time import monotonic, sleep
from uuid import UUID

import pytest
from app.db import engine
from app.models import AuditEvent, AuthSession, User
from app.security import digest
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session


def wait_for_lock(future):
    deadline = monotonic() + 5
    with engine().connect() as monitor:
        while monotonic() < deadline:
            monitor.commit()
            if monitor.scalar(
                text("""
                SELECT EXISTS(SELECT 1 FROM pg_stat_activity
                WHERE datname=current_database() AND wait_event_type='Lock'
                  AND pid<>pg_backend_pid())
                """)
            ):
                return
            if future.done():
                break
            sleep(0.01)
    pytest.fail("Refresh did not wait for the held PostgreSQL lock")


@pytest.mark.parametrize("change", ["expire", "revoke"])
def test_refresh_rechecks_locked_session(world, change):
    client, tokens, _, users = world
    token = tokens[0]["Authorization"].removeprefix("Bearer ")
    with Session(engine()) as gate, ThreadPoolExecutor(max_workers=1) as pool:
        session = gate.scalar(
            select(AuthSession).where(AuthSession.token_hash == digest(token)).with_for_update()
        )
        future = pool.submit(client.post, "/api/v1/auth/refresh", headers=tokens[0])
        try:
            wait_for_lock(future)
            if change == "expire":
                session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            else:
                gate.delete(session)
            gate.commit()
        finally:
            gate.rollback()
        response = future.result(timeout=5)
    assert response.status_code == 401, response.text
    with Session(engine()) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuthSession)
                .where(
                    AuthSession.user_id == UUID(users[0]), AuthSession.token_hash != digest(token)
                )
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.actor_id == UUID(users[0]), AuditEvent.action == "refresh")
            )
            == 0
        )
    assert client.get("/api/v1/auth/me", headers=tokens[1]).status_code == 200


@pytest.mark.parametrize("change", ["password_revocation", "deactivate"])
def test_refresh_serializes_with_user_security_changes(world, change):
    client, tokens, _, users = world
    with Session(engine()) as gate, ThreadPoolExecutor(max_workers=1) as pool:
        user = gate.scalar(select(User).where(User.id == UUID(users[0])).with_for_update())
        future = pool.submit(client.post, "/api/v1/auth/refresh", headers=tokens[0])
        try:
            wait_for_lock(future)
            if change == "password_revocation":
                # Same user-before-session lock order as the password-change endpoint.
                gate.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
            else:
                user.active = False
            gate.commit()
        finally:
            gate.rollback()
        response = future.result(timeout=5)
    assert response.status_code == 401, response.text
    assert client.get("/api/v1/auth/me", headers=tokens[0]).status_code == 401
    with Session(engine()) as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.actor_id == UUID(users[0]), AuditEvent.action == "refresh")
            )
            == 0
        )
    assert client.get("/api/v1/auth/me", headers=tokens[1]).status_code == 200


@pytest.mark.parametrize("following", ["password_change", "refresh"])
def test_rotation_winner_is_still_revoked_or_single_use(world, monkeypatch, following):
    from threading import Event

    from app.modules import identity

    client, tokens, _, users = world
    rotating, release = Event(), Event()
    original = identity.issue_session

    def pause_before_issuance(*args, **kwargs):
        rotating.set()
        assert release.wait(timeout=10), "Test did not release rotation"
        return original(*args, **kwargs)

    monkeypatch.setattr(identity, "issue_session", pause_before_issuance)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.post, "/api/v1/auth/refresh", headers=tokens[0])
        assert rotating.wait(timeout=5)
        if following == "password_change":
            second = pool.submit(
                client.put,
                "/api/v1/auth/password",
                headers=tokens[0],
                json={
                    "current_password": "Strong-password-123",
                    "new_password": "Changed-password-456",
                },
            )
        else:
            second = pool.submit(client.post, "/api/v1/auth/refresh", headers=tokens[0])
        try:
            wait_for_lock(second)
        finally:
            release.set()
        winner, follower = first.result(timeout=5), second.result(timeout=5)
    assert winner.status_code == 200
    assert follower.status_code == (200 if following == "password_change" else 401)
    fresh = {"Authorization": "Bearer " + winner.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=tokens[0]).status_code == 401
    assert client.get("/api/v1/auth/me", headers=fresh).status_code == (
        401 if following == "password_change" else 200
    )
    with Session(engine()) as db:
        assert db.scalar(
            select(func.count())
            .select_from(AuthSession)
            .where(AuthSession.user_id == UUID(users[0]))
        ) == (0 if following == "password_change" else 1)
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.actor_id == UUID(users[0]), AuditEvent.action == "refresh")
            )
            == 1
        )
    assert client.get("/api/v1/auth/me", headers=tokens[1]).status_code == 200
