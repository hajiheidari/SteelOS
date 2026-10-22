import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import database
from app.models import AuthSession, Membership, User

hasher = PasswordHasher()
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
bearer = HTTPBearer(auto_error=False)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify(password: str, hashed: str) -> bool:
    try:
        return hasher.verify(hashed, password)
    except (VerificationError, InvalidHashError):
        return False


@dataclass
class Context:
    user_id: UUID
    organization_id: UUID
    role: str
    session: AuthSession


def context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(database),
) -> Context:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Authentication required")
    row = db.execute(
        select(AuthSession, Membership, User)
        .join(
            Membership,
            (Membership.organization_id == AuthSession.organization_id)
            & (Membership.user_id == AuthSession.user_id),
        )
        .join(User, User.id == AuthSession.user_id)
        .where(
            AuthSession.token_hash == digest(credentials.credentials),
            AuthSession.expires_at > datetime.now(UTC),
            User.active.is_(True),
        )
    ).first()
    if not row:
        raise HTTPException(401, "Invalid or expired session")
    session, membership, user = row
    return Context(user.id, session.organization_id, membership.role, session)


def permit(ctx: Context, write: bool = False, admin: bool = False):
    if (admin and ctx.role != "admin") or (write and ctx.role not in ("admin", "editor")):
        raise HTTPException(403, "Permission denied")


def issue_session(db, user_id, organization_id, hours):
    token = secrets.token_urlsafe(48)
    session = AuthSession(
        user_id=user_id,
        organization_id=organization_id,
        token_hash=digest(token),
        expires_at=datetime.now(UTC) + timedelta(hours=hours),
    )
    db.add(session)
    return token, session
