"""Disposable local browser fixture, never application bootstrap credentials."""

from uuid import UUID

from app.db import engine
from app.models import Membership, Organization, User
from app.security import hasher
from sqlalchemy.orm import Session


def main():
    if not engine().url.database.endswith("_test"):
        raise SystemExit("Browser fixtures require a database ending in _test")
    with Session(engine()) as db, db.begin():
        org_id = UUID("00000000-0000-0000-0000-000000000001")
        if db.get(Organization, org_id):
            return
        org = Organization(id=org_id, name="سازمان آزمون مرورگر")
        user = User(
            email="browser@example.test", password_hash=hasher.hash("Browser-test-only-123")
        )
        db.add_all([org, user])
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role="admin"))


if __name__ == "__main__":
    main()
