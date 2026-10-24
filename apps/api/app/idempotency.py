"""Shared idempotency mechanics; callers authorize before replay and keep one transaction."""

import json

from fastapi import HTTPException
from sqlalchemy import select

from app import models as m
from app.security import digest


def replay(db, ctx, key, namespace, payload):
    fingerprint = digest(namespace + json.dumps(payload, sort_keys=True))
    prior = db.scalar(
        select(m.IdempotencyRecord).where(
            m.IdempotencyRecord.organization_id == ctx.organization_id,
            m.IdempotencyRecord.actor_id == ctx.user_id,
            m.IdempotencyRecord.key == key,
        )
    )
    if prior and prior.request_hash != fingerprint:
        raise HTTPException(409, "Idempotency key reused for another request")
    return (prior.response if prior else None), fingerprint


def finish(db, ctx, key, fingerprint, response):
    db.add(
        m.IdempotencyRecord(
            organization_id=ctx.organization_id,
            actor_id=ctx.user_id,
            key=key,
            request_hash=fingerprint,
            response=response,
        )
    )
    db.commit()
    return response
