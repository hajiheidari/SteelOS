import pytest
from conftest import create


def test_membership_permissions_and_password_revocation(world):
    client, tokens, orgs, users = world
    member = create(
        client,
        tokens[0],
        "organization/members",
        {"email": "editor@example.test", "password": "Strong-password-123", "role": "editor"},
    )
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "editor@example.test",
            "password": "Strong-password-123",
            "organization_id": orgs[0],
        },
    ).json()
    headers = {"Authorization": "Bearer " + login["access_token"]}
    create(
        client, headers, "parties", {"name": "Test", "kind": "individual", "roles": ["supplier"]}
    )
    create(
        client,
        headers,
        "warehouses",
        {"code": "X", "name": "Test", "city": "City", "address": "Address"},
        expected=403,
    )
    assert (
        client.put(
            "/api/v1/organization/members/" + member["user_id"],
            headers=tokens[0],
            json={"role": "viewer"},
        ).status_code
        == 200
    )
    create(
        client,
        headers,
        "parties",
        {"name": "Test 2", "kind": "individual", "roles": ["supplier"]},
        expected=403,
    )
    assert (
        client.put(
            "/api/v1/organization/members/" + users[1], headers=tokens[0], json={"role": "viewer"}
        ).status_code
        == 404
    )
    assert (
        client.put(
            "/api/v1/organization/members/" + users[0], headers=tokens[0], json={"role": "viewer"}
        ).status_code
        == 422
    )
    assert (
        client.put("/api/v1/organization", headers=tokens[0], json={"name": "نام جدید"}).status_code
        == 200
    )
    assert (
        client.get("/api/v1/auth/me", headers=tokens[0]).json()["organization"]["name"]
        == "نام جدید"
    )
    assert (
        client.put(
            "/api/v1/auth/password",
            headers=headers,
            json={
                "current_password": "Strong-password-123",
                "new_password": "New-strong-password-456",
            },
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "editor@example.test",
                "password": "Strong-password-123",
                "organization_id": orgs[0],
            },
        ).status_code
        == 401
    )
    assert (
        client.delete(
            "/api/v1/organization/members/" + member["user_id"], headers=tokens[1]
        ).status_code
        == 404
    )
    assert (
        client.delete(
            "/api/v1/organization/members/" + member["user_id"], headers=tokens[0]
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "editor@example.test",
                "password": "New-strong-password-456",
                "organization_id": orgs[0],
            },
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "operations", [("demote", "demote"), ("remove", "remove"), ("demote", "remove")]
)
def test_concurrent_admin_changes_preserve_an_administrator(world, monkeypatch, operations):
    """Both requests authenticate before either mutates the other's membership."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from uuid import UUID

    from app.db import engine
    from app.models import Membership
    from app.modules import identity
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    client, tokens, orgs, users = world
    assert (
        client.put(
            "/api/v1/organization/members/" + users[2], headers=tokens[0], json={"role": "admin"}
        ).status_code
        == 200
    )
    authenticated = Barrier(2)
    original_permit = identity.permit

    def synchronize(ctx, **kwargs):
        original_permit(ctx, **kwargs)
        authenticated.wait(timeout=10)

    monkeypatch.setattr(identity, "permit", synchronize)

    def demote(pair):
        actor, target, operation = pair
        path = "/api/v1/organization/members/" + users[target]
        if operation == "remove":
            return client.delete(path, headers=tokens[actor]).status_code
        return client.put(path, headers=tokens[actor], json={"role": "viewer"}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(demote, [(0, 2, operations[0]), (2, 0, operations[1])]))
    assert sorted(results) == [200, 403]
    with Session(engine()) as db:
        admins = db.scalars(
            select(Membership).where(
                Membership.organization_id == UUID(orgs[0]), Membership.role == "admin"
            )
        ).all()
        assert len(admins) == 1
