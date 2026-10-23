from uuid import UUID

from app import models as m
from app.db import database
from app.modules.inventory import service as domain
from app.modules.inventory.schemas import DraftInput, LotInput
from app.modules.resources import audit, get_row, scoped, serialize
from app.security import Context, authorize_write, context
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/inventory", tags=["inventory"])
Key = Header(..., min_length=1, max_length=100)


@router.post("/lots", status_code=201)
def create_lot(
    payload: LotInput,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx)
    product = get_row(db, m.Product, ctx, payload.product_id, lock=True)
    data = payload.model_dump()
    data["code"] = data["code"].upper()
    prior, fingerprint = domain.replay(
        db, ctx, idempotency_key, "inventory/lots", payload.model_dump(mode="json")
    )
    if prior:
        return prior
    lot = m.StockLot(organization_id=ctx.organization_id, **data)
    domain.active_lot(db, ctx, lot)
    if product.unit != payload.unit:
        from fastapi import HTTPException

        raise HTTPException(422, "Lot unit must match product unit")
    db.add(lot)
    db.flush()
    audit(db, ctx, "create", "inventory-lots", lot.id)
    return domain.finish(db, ctx, idempotency_key, fingerprint, serialize(lot))


@router.post("/drafts", status_code=201)
def create_draft(
    payload: DraftInput,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx)
    lot = domain.record(db, m.StockLot, ctx, payload.lot_id)
    data = domain.draft_data(db, ctx, payload, lot)
    prior, fingerprint = domain.replay(
        db, ctx, idempotency_key, "inventory/drafts", payload.model_dump(mode="json")
    )
    if prior:
        domain.record(db, m.StockDraft, ctx, UUID(prior["id"]))
        return prior
    draft = m.StockDraft(organization_id=ctx.organization_id, created_by=ctx.user_id, **data)
    db.add(draft)
    db.flush()
    audit(db, ctx, "create", "inventory-drafts", draft.id)
    return domain.finish(db, ctx, idempotency_key, fingerprint, serialize(draft))


@router.post("/drafts/{draft_id}/post")
def post_draft(
    draft_id: UUID,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx, admin=True)
    prior, fingerprint = domain.replay(db, ctx, idempotency_key, f"inventory/{draft_id}/post", {})
    if prior:
        return prior
    draft = domain.post(db, ctx, draft_id)
    return domain.finish(db, ctx, idempotency_key, fingerprint, serialize(draft))


@router.post("/drafts/{draft_id}/reject")
def reject_draft(
    draft_id: UUID,
    idempotency_key: str = Key,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    from fastapi import HTTPException

    authorize_write(db, ctx, admin=True)
    prior, fingerprint = domain.replay(db, ctx, idempotency_key, f"inventory/{draft_id}/reject", {})
    if prior:
        return prior
    draft = domain.record(db, m.StockDraft, ctx, draft_id, lock=True)
    if draft.status == "posted":
        raise HTTPException(409, "Posted movement cannot be rejected")
    if draft.status == "draft":
        draft.status = "rejected"
        db.flush()
        audit(db, ctx, "inventory_reject", "inventory-drafts", draft.id)
    return domain.finish(db, ctx, idempotency_key, fingerprint, serialize(draft))


def register_list(path, model):
    def list_rows(
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        lot_id: UUID | None = None,
        product_id: UUID | None = None,
        warehouse_id: UUID | None = None,
        status: str | None = None,
        ctx: Context = Depends(context),
        db: Session = Depends(database),
    ):
        from fastapi import HTTPException

        stmt = domain.visible(scoped(model, ctx), model, ctx)
        for field, value in (("lot_id", lot_id), ("product_id", product_id), ("status", status)):
            if value is not None:
                if not hasattr(model, field):
                    raise HTTPException(422, "Unsupported inventory filter")
                stmt = stmt.where(getattr(model, field) == value)
        if warehouse_id:
            if model is m.StockDraft:
                from sqlalchemy import or_

                stmt = stmt.where(
                    or_(
                        model.from_warehouse_id == warehouse_id,
                        model.to_warehouse_id == warehouse_id,
                    )
                )
            elif hasattr(model, "warehouse_id"):
                stmt = stmt.where(model.warehouse_id == warehouse_id)
            else:
                raise HTTPException(422, "Unsupported inventory warehouse filter")
        total = db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = db.scalars(
            stmt.order_by(model.created_at.desc(), model.id).offset(offset).limit(limit)
        ).all()
        items = []
        for row in rows:
            item = serialize(row)
            if model is m.StockReservation:
                remaining = domain.reservation_remaining(db, ctx, row.id)
                item["remaining"] = str(remaining)
                item["expired"] = row.expires_at <= domain.now(db)
            items.append(item)
        return {"items": items, "total": total, "offset": offset, "limit": limit}

    def read_row(record_id: UUID, ctx: Context = Depends(context), db: Session = Depends(database)):
        return serialize(domain.record(db, model, ctx, record_id))

    router.add_api_route("/" + path, list_rows, methods=["GET"], name="list_inventory_" + path)
    router.add_api_route(
        "/" + path + "/{record_id}", read_row, methods=["GET"], name="read_inventory_" + path
    )


for path, model in (
    ("lots", m.StockLot),
    ("drafts", m.StockDraft),
    ("entries", m.StockEntry),
    ("reservations", m.StockReservation),
):
    register_list(path, model)


@router.get("/balances")
def balances(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    lot_id: UUID | None = None,
    warehouse_id: UUID | None = None,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    entry, reservation, lot = m.StockEntry, m.StockReservation, m.StockLot
    at = domain.now(db)
    hand = func.sum(entry.on_hand_delta).label("on_hand")
    blocked = func.sum(entry.blocked_delta).label("blocked")
    reserved = func.sum(
        case((reservation.expires_at > at, entry.reserved_delta), else_=domain.ZERO)
    ).label("reserved")
    stmt = (
        select(
            entry.lot_id,
            entry.warehouse_id,
            entry.location_id,
            lot.code,
            lot.product_id,
            lot.owner_kind,
            lot.owner_party_id,
            lot.unit,
            hand,
            blocked,
            reserved,
        )
        .join(lot, (lot.id == entry.lot_id) & (lot.organization_id == entry.organization_id))
        .outerjoin(
            reservation,
            (reservation.id == entry.reservation_id)
            & (reservation.organization_id == entry.organization_id),
        )
        .where(entry.organization_id == ctx.organization_id)
    )
    if ctx.role != "admin":
        stmt = stmt.where(entry.warehouse_id.in_(domain.allowed_warehouses(ctx)))
    if lot_id:
        stmt = stmt.where(entry.lot_id == lot_id)
    if warehouse_id:
        stmt = stmt.where(entry.warehouse_id == warehouse_id)
    stmt = stmt.group_by(entry.lot_id, entry.warehouse_id, entry.location_id, lot.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(
        stmt.order_by(entry.lot_id, entry.warehouse_id, entry.location_id)
        .offset(offset)
        .limit(limit)
    ).mappings()
    items = []
    for row in rows:
        item = {key: str(value) if value is not None else None for key, value in row.items()}
        item["available"] = str(row["on_hand"] - row["blocked"] - row["reserved"])
        items.append(item)
    return {"items": items, "total": total, "offset": offset, "limit": limit, "as_of": at}
