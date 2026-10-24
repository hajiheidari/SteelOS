from uuid import UUID

from app import models as m
from app.db import database
from app.idempotency import finish, replay
from app.modules.resources import scoped, serialize
from app.modules.sales import service
from app.modules.sales.schemas import CancelInput, DraftInput, DraftUpdate
from app.security import Context, authorize_write, context
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/sales-drafts", tags=["internal sales drafts"])
Key = Header(..., min_length=1, max_length=100)


@router.post("", status_code=201)
def create(
    payload: DraftInput,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx)
    prior, fingerprint = replay(
        db, ctx, idempotency_key, "sales-drafts/create", payload.model_dump(mode="json")
    )
    if prior:
        service.record(db, ctx, UUID(prior["id"]))
        return prior
    lines, at = service.prepare(db, ctx, payload)
    draft = m.SalesDraft(
        organization_id=ctx.organization_id,
        code=payload.code.upper(),
        customer_id=payload.customer_id,
        currency=payload.currency,
        note=payload.note,
        amount_rounding="half_up_2",
        tax_rate_percent=(
            payload.tax_rate_percent
            if payload.tax_rate_percent is not None
            else service.default_tax_rate(db, ctx)
        ),
        created_by=ctx.user_id,
        updated_by=ctx.user_id,
        updated_at=at,
    )
    db.add(draft)
    db.flush()
    service.replace_lines(db, ctx, draft, lines)
    return finish(db, ctx, idempotency_key, fingerprint, service.revise(db, ctx, draft, "create"))


@router.put("/{draft_id}")
def update(
    draft_id: UUID,
    payload: DraftUpdate,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx)
    prior, fingerprint = replay(
        db, ctx, idempotency_key, f"sales-drafts/{draft_id}/update", payload.model_dump(mode="json")
    )
    draft = service.record(db, ctx, draft_id, lock=True)
    if prior:
        return prior
    service.change(db, ctx, draft, payload.expected_version)
    if payload.code.upper() != draft.code:
        raise HTTPException(422, "Sales draft code is immutable")
    lines, at = service.prepare(db, ctx, payload)
    rate = payload.tax_rate_percent
    if rate is None:
        rate = draft.tax_rate_percent
    if rate is None:
        rate = service.default_tax_rate(db, ctx)
    draft.customer_id, draft.currency, draft.note = (
        payload.customer_id,
        payload.currency,
        payload.note,
    )
    draft.tax_rate_percent = rate
    draft.amount_rounding = "half_up_2"
    draft.version += 1
    draft.updated_by, draft.updated_at = ctx.user_id, at
    db.flush()
    service.replace_lines(db, ctx, draft, lines)
    return finish(db, ctx, idempotency_key, fingerprint, service.revise(db, ctx, draft, "update"))


@router.post("/{draft_id}/cancel")
def cancel(
    draft_id: UUID,
    payload: CancelInput,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx)
    prior, fingerprint = replay(
        db, ctx, idempotency_key, f"sales-drafts/{draft_id}/cancel", payload.model_dump(mode="json")
    )
    draft = service.record(db, ctx, draft_id, lock=True)
    if prior:
        return prior
    service.change(db, ctx, draft, payload.expected_version)
    at = service.now(db)
    draft.status, draft.version = "cancelled", draft.version + 1
    draft.updated_by, draft.updated_at = ctx.user_id, at
    return finish(db, ctx, idempotency_key, fingerprint, service.revise(db, ctx, draft, "cancel"))


@router.get("")
def list_drafts(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    q: str = Query("", max_length=200),
    status: str | None = Query(None, pattern="^(draft|cancelled)$"),
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    stmt = scoped(m.SalesDraft, ctx)
    if q.strip():
        stmt = stmt.where(
            or_(
                m.SalesDraft.code.icontains(q.strip(), autoescape=True),
                m.SalesDraft.customer_id.in_(
                    select(m.Party.id).where(
                        m.Party.organization_id == ctx.organization_id,
                        m.Party.name.icontains(q.strip(), autoescape=True),
                    )
                ),
            )
        )
    if status:
        stmt = stmt.where(m.SalesDraft.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    drafts = db.scalars(
        stmt.order_by(m.SalesDraft.created_at.desc(), m.SalesDraft.id).offset(offset).limit(limit)
    ).all()
    customers = service.rows_by_id(db, ctx, m.Party, {row.customer_id for row in drafts})
    base = func.round(m.SalesDraftLine.quantity * m.SalesDraftLine.unit_price, 2)
    tax = func.round(base * m.SalesDraft.tax_rate_percent / 100, 2)
    stats = (
        {
            row.draft_id: row
            for row in db.execute(
                select(
                    m.SalesDraftLine.draft_id,
                    func.count().label("line_count"),
                    func.sum(m.SalesDraftLine.quantity * m.SalesDraftLine.unit_price).label(
                        "amount"
                    ),
                    func.min(m.SalesDraftLine.price_valid_until).label("valid_until"),
                    func.sum(base).label("subtotal"),
                    func.sum(tax).label("tax_total"),
                    func.sum(base + tax).label("grand_total"),
                )
                .join(
                    m.SalesDraft,
                    (m.SalesDraft.id == m.SalesDraftLine.draft_id)
                    & (m.SalesDraft.organization_id == m.SalesDraftLine.organization_id),
                )
                .where(
                    m.SalesDraftLine.organization_id == ctx.organization_id,
                    m.SalesDraftLine.draft_id.in_([row.id for row in drafts]),
                )
                .group_by(m.SalesDraftLine.draft_id)
            )
        }
        if drafts
        else {}
    )
    items, at = [], service.now(db)
    for row in drafts:
        item, stat = serialize(row), stats[row.id]
        item.update(
            customer_name=customers[row.customer_id].name,
            line_count=stat.line_count,
            estimated_total=format(stat.amount, ".9f"),
            has_expired_price=stat.valid_until <= at,
            financial_approval=False,
            invoice_policy=service.invoice_policy(row.currency),
        )
        configured = row.tax_rate_percent is not None and row.amount_rounding == "half_up_2"
        item.update(
            {
                key: format(getattr(stat, key), ".2f") if configured else None
                for key in ("subtotal", "tax_total", "grand_total")
            }
        )
        items.append(item)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{draft_id}")
def read(draft_id: UUID, ctx: Context = Depends(context), db: Session = Depends(database)):
    return service.details(db, ctx, service.record(db, ctx, draft_id))


@router.get("/{draft_id}/revisions")
def revisions(
    draft_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    service.record(db, ctx, draft_id)
    stmt = scoped(m.SalesDraftRevision, ctx).where(m.SalesDraftRevision.draft_id == draft_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(m.SalesDraftRevision.version.desc()).offset(offset).limit(limit)
    )
    return {
        "items": [
            {key: value for key, value in serialize(row).items() if key != "snapshot"}
            for row in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{draft_id}/revisions/{version}")
def revision(
    draft_id: UUID, version: int, ctx: Context = Depends(context), db: Session = Depends(database)
):
    service.record(db, ctx, draft_id)
    row = db.scalar(
        scoped(m.SalesDraftRevision, ctx).where(
            m.SalesDraftRevision.draft_id == draft_id, m.SalesDraftRevision.version == version
        )
    )
    if not row:
        raise HTTPException(404, "Sales draft revision not found")
    return serialize(row)
