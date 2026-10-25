"""Local untrusted intake and human transcription review; never a financial posting API."""

import hashlib
import threading
from datetime import UTC, datetime
from uuid import UUID

import anyio
from app.db import database
from app.idempotency import finish, replay
from app.modules.invoices import ocr
from app.modules.invoices.models import InvoiceIntake, InvoiceIntakeRevision
from app.modules.invoices.parser import propose
from app.modules.invoices.schemas import IntakeUpdate
from app.modules.resources import audit, scoped, serialize
from app.security import Context, authorize_write, bearer, context, permit
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/invoice-intakes", tags=["untrusted invoice intake"])
slots = threading.BoundedSemaphore(2)
Key = Header(..., min_length=1, max_length=100)


def record(db, ctx, intake_id, lock=False):
    stmt = scoped(InvoiceIntake, ctx).where(InvoiceIntake.id == intake_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(stmt)
    if not row:
        raise HTTPException(404, "Invoice intake not found")
    return row


def detail(row):
    return {**serialize(row), "financial_approval": False, "business_posted": False}


def revise(db, ctx, row, action):
    db.flush()
    response = detail(row)
    db.add(
        InvoiceIntakeRevision(
            organization_id=ctx.organization_id,
            intake_id=row.id,
            version=row.version,
            actor_id=ctx.user_id,
            snapshot=response,
        )
    )
    audit(db, ctx, action, "invoice-intakes", row.id)
    return response


@router.get("/status")
def status(ctx: Context = Depends(context)):
    return {
        "available": ocr.availability(),
        "max_bytes": ocr.MAX_BYTES,
        "max_pages": 3,
        "media_types": ["image/png", "image/jpeg", "application/pdf"],
        "financial_approval": False,
    }


@router.post(
    "/extract",
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in ("image/png", "image/jpeg", "application/pdf")
            },
        }
    },
)
async def extract(
    request: Request,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    credentials=Depends(bearer),
    db: Session = Depends(database),
):
    permit(ctx, write=True)
    media = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media not in ("image/png", "image/jpeg", "application/pdf"):
        raise HTTPException(415, "Upload PNG, JPEG or PDF bytes")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > ocr.MAX_BYTES:
            raise HTTPException(413, "Document exceeds5MiB")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(422, "Empty document")
    source_hash = hashlib.sha256(data).hexdigest()
    payload = {"sha256": source_hash, "media_type": media}
    authorize_write(db, ctx)
    prior, _ = replay(db, ctx, idempotency_key, "invoice-intakes/extract", payload)
    if prior:
        record(db, ctx, UUID(prior["id"]))
        return prior
    if db.scalar(scoped(InvoiceIntake, ctx).where(InvoiceIntake.source_sha256 == source_hash)):
        raise HTTPException(409, "Document already exists in this organization")
    db.rollback()  # No actor/DB locks or connections held through native OCR.
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Local OCR is busy; retry later")
    try:
        raw, pages, engine = await anyio.to_thread.run_sync(ocr.extract, data, media)
    finally:
        slots.release()
    # Reauthenticate after processing: removed/revoked/expired sessions cannot persist output.
    ctx = context(credentials, db)
    authorize_write(db, ctx)
    prior, fingerprint = replay(db, ctx, idempotency_key, "invoice-intakes/extract", payload)
    if prior:
        record(db, ctx, UUID(prior["id"]))
        return prior
    extraction = propose(raw)
    row = InvoiceIntake(
        organization_id=ctx.organization_id,
        source_sha256=source_hash,
        media_type=media,
        page_count=pages,
        engine=engine,
        raw_text=raw,
        extraction=extraction,
        corrected_text=raw,
        fields=extraction["fields"],
        status="draft",
        version=1,
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
    )
    db.add(row)
    return finish(db, ctx, idempotency_key, fingerprint, revise(db, ctx, row, "extract_invoice"))


@router.get("")
def listing(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    stmt = scoped(InvoiceIntake, ctx)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(InvoiceIntake.created_at.desc(), InvoiceIntake.id).offset(offset).limit(limit)
    )
    return {
        "items": [
            {
                "id": row.id,
                "version": row.version,
                "status": row.status,
                "created_at": row.created_at,
                "invoice_number": row.fields.get("invoice_number"),
                "financial_approval": False,
            }
            for row in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{intake_id}")
def read(intake_id: UUID, ctx: Context = Depends(context), db: Session = Depends(database)):
    return detail(record(db, ctx, intake_id))


@router.put("/{intake_id}")
def update(
    intake_id: UUID,
    payload: IntakeUpdate,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx)
    prior, fingerprint = replay(
        db,
        ctx,
        idempotency_key,
        f"invoice-intakes/{intake_id}/update",
        payload.model_dump(mode="json"),
    )
    row = record(db, ctx, intake_id, lock=True)
    if prior:
        return prior
    if row.version != payload.expected_version:
        raise HTTPException(409, "Invoice intake version changed; reload")
    row.corrected_text, row.fields = payload.corrected_text, payload.fields.model_dump(mode="json")
    row.status = "reviewed" if payload.mark_reviewed else "draft"
    row.version += 1
    row.updated_by, row.updated_at = ctx.user_id, datetime.now(UTC)
    return finish(
        db,
        ctx,
        idempotency_key,
        fingerprint,
        revise(
            db, ctx, row, "review_transcription" if payload.mark_reviewed else "edit_transcription"
        ),
    )


@router.get("/{intake_id}/revisions")
def revisions(
    intake_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    record(db, ctx, intake_id)
    stmt = scoped(InvoiceIntakeRevision, ctx).where(InvoiceIntakeRevision.intake_id == intake_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(InvoiceIntakeRevision.version.desc()).offset(offset).limit(limit)
    )
    return {
        "items": [
            {
                "id": row.id,
                "version": row.version,
                "actor_id": row.actor_id,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/{intake_id}/revisions/{version}")
def revision(
    intake_id: UUID, version: int, ctx: Context = Depends(context), db: Session = Depends(database)
):
    record(db, ctx, intake_id)
    row = db.scalar(
        scoped(InvoiceIntakeRevision, ctx).where(
            InvoiceIntakeRevision.intake_id == intake_id, InvoiceIntakeRevision.version == version
        )
    )
    if not row:
        raise HTTPException(404, "Revision not found")
    return row.snapshot
