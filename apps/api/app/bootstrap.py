"""Explicit local operator command; no publicly accessible signup endpoint."""

import argparse
import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import engine
from app.models import Membership, Organization, User
from app.schemas import NewMember
from app.security import hasher


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    member = NewMember(
        email=args.email.lower(), password=getpass.getpass("Password: "), role="admin"
    )
    with Session(engine()) as db, db.begin():
        if db.scalar(select(User).where(User.email == member.email)):
            raise SystemExit("User exists; use organization administration instead")
        org = Organization(name=args.organization)
        user = User(email=member.email, password_hash=hasher.hash(member.password))
        db.add_all([org, user])
        db.flush()
        db.add(Membership(organization_id=org.id, user_id=user.id, role="admin"))
        print(f"Organization ID: {org.id}")


if __name__ == "__main__":
    main()
