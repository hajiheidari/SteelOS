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
