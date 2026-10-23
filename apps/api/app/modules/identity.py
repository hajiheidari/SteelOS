from datetime import UTC, datetime, timedelta
from uuid import UUID

from app import models as m
from app import schemas as s
from app.config import settings
from app.db import database
from app.modules.resources import audit
from app.security import (
    DUMMY_HASH,
    Context,
    context,
    digest,
    hasher,
    issue_session,
    permit,
    verify,
)
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(tags=["identity"])


def require_organization_admin(db: Session, ctx: Context):
    """Serialize administration and recheck authority after waiting for the lock.

    Self-demotion/removal is forbidden. Rechecking the actor ensures two admins
    cannot concurrently remove or demote one another and leave no administrator.
    The organization lock is held until the enclosing transaction completes.
    """
    permit(ctx, admin=True)
    db.execute(
        select(m.Organization.id)
        .where(m.Organization.id == ctx.organization_id)
        # NO KEY UPDATE serializes admins without blocking ordinary FK inserts.
        .with_for_update(key_share=True)
    )
    role = db.scalar(
        select(m.Membership.role).where(
            m.Membership.organization_id == ctx.organization_id,
            m.Membership.user_id == ctx.user_id,
        )
    )
    if role != "admin":
        raise HTTPException(403, "Administrator permission changed; reload your session")


@router.post("/auth/login")
def login(payload: s.Login, db: Session = Depends(database)):
    email = payload.email.lower()
    key = digest(email)
    # Upsert then row lock ensures rate limits apply across API workers.
    from sqlalchemy.dialects.postgresql import insert

    now = datetime.now(UTC)
    db.execute(
        insert(m.LoginAttempt)
        .values(key=key, failures=0, window_start=now)
        .on_conflict_do_nothing()
    )
    attempt = db.scalar(select(m.LoginAttempt).where(m.LoginAttempt.key == key).with_for_update())
    if attempt.window_start < now - timedelta(minutes=15):
        attempt.failures, attempt.window_start = 0, now
    if attempt.failures >= 10:
        db.commit()
        raise HTTPException(429, "Too many login attempts; retry in 15 minutes")
    user = db.scalar(select(m.User).where(m.User.email == email).with_for_update())
    valid = verify(payload.password, user.password_hash if user else DUMMY_HASH)
    member = (
        db.scalar(
            select(m.Membership).where(
                m.Membership.user_id == user.id,
                m.Membership.organization_id == payload.organization_id,
            )
        )
        if user
        else None
    )
    if not valid or not member or not user.active:
        attempt.failures += 1
        db.commit()
        raise HTTPException(401, "Invalid credentials or organization")
    attempt.failures = 0
    if hasher.check_needs_rehash(user.password_hash):
        user.password_hash = hasher.hash(payload.password)
    token, session = issue_session(db, user.id, member.organization_id, settings().session_hours)
    ctx = Context(user.id, member.organization_id, member.role, session)
    audit(db, ctx, "login", "users", user.id)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_at": session.expires_at}


@router.get("/auth/me")
def me(ctx: Context = Depends(context), db: Session = Depends(database)):
    user = db.get(m.User, ctx.user_id)
    org = db.get(m.Organization, ctx.organization_id)
    return {
        "id": ctx.user_id,
        "email": user.email,
        "role": ctx.role,
        "organization": {"id": org.id, "name": org.name},
        "permissions": ["read"]
        + (["write"] if ctx.role in ("admin", "editor") else [])
        + (["admin", "price:approve", "warehouse:manage"] if ctx.role == "admin" else []),
    }


@router.post("/auth/logout")
def logout(ctx: Context = Depends(context), db: Session = Depends(database)):
    audit(db, ctx, "logout", "users", ctx.user_id)
    db.delete(ctx.session)
    db.commit()
    return {"revoked": True}


@router.post("/auth/refresh")
def refresh(ctx: Context = Depends(context), db: Session = Depends(database)):
    # Row lock and recheck makes rotation single use under concurrent retries.
    session = db.scalar(
        select(m.AuthSession).where(m.AuthSession.id == ctx.session.id).with_for_update()
    )
    if not session:
        raise HTTPException(401, "Session already rotated")
    token, new_session = issue_session(
        db, ctx.user_id, ctx.organization_id, settings().session_hours
    )
    db.delete(session)
    audit(db, ctx, "refresh", "users", ctx.user_id)
    db.commit()
    return {"access_token": token, "token_type": "bearer", "expires_at": new_session.expires_at}


@router.get("/organization/members")
def members(ctx: Context = Depends(context), db: Session = Depends(database)):
    permit(ctx, admin=True)
    rows = db.execute(
        select(m.Membership, m.User)
        .join(m.User, m.User.id == m.Membership.user_id)
        .where(m.Membership.organization_id == ctx.organization_id)
    ).all()
    return {
        "items": [{"user_id": u.id, "email": u.email, "role": member.role} for member, u in rows]
    }


@router.post("/organization/members", status_code=201)
def add_member(
    payload: s.NewMember, ctx: Context = Depends(context), db: Session = Depends(database)
):
    require_organization_admin(db, ctx)
    email = payload.email.lower()
    if db.scalar(select(m.User).where(m.User.email == email).with_for_update()):
        raise HTTPException(
            409, "Email already exists; cross-organization enrollment requires operator review"
        )
    user = m.User(email=email, password_hash=hasher.hash(payload.password))
    db.add(user)
    db.flush()
    db.add(m.Membership(user_id=user.id, organization_id=ctx.organization_id, role=payload.role))
    audit(db, ctx, "create_member", "users", user.id)
    db.commit()
    return {"user_id": user.id, "email": user.email, "role": payload.role}


@router.delete("/organization/members/{user_id}")
def remove_member(user_id: UUID, ctx: Context = Depends(context), db: Session = Depends(database)):
    require_organization_admin(db, ctx)
    if user_id == ctx.user_id:
        raise HTTPException(422, "Cannot remove own membership")
    member = db.scalar(
        select(m.Membership).where(
            m.Membership.organization_id == ctx.organization_id, m.Membership.user_id == user_id
        )
    )
    if not member:
        raise HTTPException(404, "Member not found")
    for model in (m.AuthSession, m.WarehouseAccess):
        for row in db.scalars(
            select(model).where(
                model.organization_id == ctx.organization_id, model.user_id == user_id
            )
        ):
            db.delete(row)
    db.flush()
    db.delete(member)
    audit(db, ctx, "remove_member", "users", user_id)
    db.commit()
    return {"deleted": True}


@router.put("/organization")
def update_organization(
    payload: s.OrganizationUpdate, ctx: Context = Depends(context), db: Session = Depends(database)
):
    require_organization_admin(db, ctx)
    org = db.get(m.Organization, ctx.organization_id)
    org.name = payload.name
    audit(db, ctx, "update", "organizations", org.id)
    db.commit()
    return {"id": org.id, "name": org.name}


@router.put("/auth/password")
def change_password(
    payload: s.PasswordUpdate, ctx: Context = Depends(context), db: Session = Depends(database)
):
    user = db.scalar(select(m.User).where(m.User.id == ctx.user_id).with_for_update())
    if not verify(payload.current_password, user.password_hash):
        raise HTTPException(401, "Invalid current password")
    user.password_hash = hasher.hash(payload.new_password)
    for session in db.scalars(select(m.AuthSession).where(m.AuthSession.user_id == ctx.user_id)):
        db.delete(session)
    audit(db, ctx, "password_change", "users", user.id)
    db.commit()
    return {"revoked": True}


@router.put("/organization/members/{user_id}")
def update_role(
    user_id: UUID,
    payload: s.RoleUpdate,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    require_organization_admin(db, ctx)
    if user_id == ctx.user_id:
        raise HTTPException(422, "Cannot change own role; another administrator must review")
    row = db.scalar(
        select(m.Membership)
        .where(m.Membership.organization_id == ctx.organization_id, m.Membership.user_id == user_id)
        .with_for_update()
    )
    if not row:
        raise HTTPException(404, "Member not found")
    row.role = payload.role
    audit(db, ctx, "role_change", "users", user_id)
    db.commit()
    return {"user_id": row.user_id, "role": row.role}
