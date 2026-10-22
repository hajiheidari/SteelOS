import uuid

import pytest
from app.db import Base, engine
from app.main import app
from app.models import Membership, Organization, User
from app.security import hasher
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def world():
    # Dedicated disposable PostgreSQL database only; migrate before running tests.
    with engine().begin() as conn:
        tables = ", ".join('"' + t.name + '"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))
    with Session(engine()) as db:
        orgs = [Organization(name=f"Organization {i}") for i in range(2)]
        users = [
            User(email=f"user{i}@example.test", password_hash=hasher.hash("Strong-password-123"))
            for i in range(3)
        ]
        db.add_all([*orgs, *users])
        db.flush()
        for i, role in enumerate(("admin", "admin", "viewer")):
            db.add(
                Membership(
                    organization_id=orgs[1 if i == 1 else 0].id, user_id=users[i].id, role=role
                )
            )
        db.commit()
        org_ids = [str(org.id) for org in orgs]
        user_ids = [str(user.id) for user in users]
    with TestClient(app) as client:
        tokens = []
        for i in range(3):
            result = client.post(
                "/api/v1/auth/login",
                json={
                    "email": f"user{i}@example.test",
                    "password": "Strong-password-123",
                    "organization_id": org_ids[1 if i == 1 else 0],
                },
            )
            assert result.status_code == 200, result.text
            tokens.append({"Authorization": "Bearer " + result.json()["access_token"]})
        yield client, tokens, org_ids, user_ids


def create(client, headers, resource, payload, expected=201, key=None):
    result = client.post(
        "/api/v1/" + resource,
        headers={**headers, "Idempotency-Key": key or str(uuid.uuid4())},
        json=payload,
    )
    assert result.status_code == expected, result.text
    return result.json()


@pytest.fixture
def catalog(world):
    client, headers, _, _ = world
    category = create(
        client,
        headers[0],
        "catalog-references",
        {
            "kind": "category",
            "code": "sheet",
            "name": "ورق",
            "attribute_rules": {"thickness": {"unit": "mm", "required": True}},
        },
    )
    payload = {
        "sku": "sheet-2",
        "name": "ورق دو میلیمتر",
        "category_id": category["id"],
        "unit": "kg",
        "attributes": {"thickness": {"value": "2.00", "unit": "mm"}},
    }
    product = create(client, headers[0], "products", payload)
    return category, payload, product
