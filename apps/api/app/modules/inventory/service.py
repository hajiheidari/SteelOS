"""Transactional stock operations. Every effect is an immutable signed ledger entry."""

import json
from decimal import Decimal

from app import models as m
from app.modules.resources import audit, get_row, scoped, warehouse_allowed
from app.security import digest
from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select

ZERO = Decimal("0")
MAX_QUANTITY = Decimal("99999999999999999.999")


def now(db):
    return db.scalar(select(func.clock_timestamp()))


def allowed_warehouses(ctx):
    return select(m.WarehouseAccess.warehouse_id).where(
        m.WarehouseAccess.organization_id == ctx.organization_id,
        m.WarehouseAccess.user_id == ctx.user_id,
    )


def visible(stmt, model, ctx):
    if ctx.role == "admin":
        return stmt
    ids = allowed_warehouses(ctx)
    if model is m.StockDraft:
        return stmt.where(
            or_(model.from_warehouse_id.is_(None), model.from_warehouse_id.in_(ids)),
            or_(model.to_warehouse_id.is_(None), model.to_warehouse_id.in_(ids)),
        )
    if model is m.StockLot:
        if ctx.role == "editor":
            return stmt  # Lot identity alone has no physical balance or location.
        return stmt.where(
            select(m.StockEntry.id)
            .where(
                m.StockEntry.organization_id == ctx.organization_id,
                m.StockEntry.lot_id == m.StockLot.id,
                m.StockEntry.warehouse_id.in_(ids),
            )
            .exists()
        )
    return stmt.where(model.warehouse_id.in_(ids))


def record(db, model, ctx, record_id, *, lock=False):
    stmt = visible(scoped(model, ctx), model, ctx).where(model.id == record_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(stmt)
    if not row:
        raise HTTPException(404, "Inventory record not found")
    return row


def active_lot(db, ctx, lot):
    product = get_row(db, m.Product, ctx, lot.product_id)
    if not product.active or product.unit != lot.unit:
        raise HTTPException(409, "Lot product is inactive or unit changed")
    if lot.owner_party_id and not get_row(db, m.Party, ctx, lot.owner_party_id).active:
        raise HTTPException(409, "Lot owner is inactive")


def location(db, ctx, location_id):
    row = get_row(db, m.Location, ctx, location_id)
    warehouse_allowed(db, ctx, row.warehouse_id)
    if not get_row(db, m.Warehouse, ctx, row.warehouse_id).active:
        raise HTTPException(409, "Warehouse is inactive")
    return row


def replay(db, ctx, key, namespace, payload):
    fingerprint = digest(namespace + json.dumps(payload, sort_keys=True))
    prior = db.scalar(
        scoped(m.IdempotencyRecord, ctx).where(
            m.IdempotencyRecord.actor_id == ctx.user_id, m.IdempotencyRecord.key == key
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


def draft_data(db, ctx, payload, lot):
    active_lot(db, ctx, lot)
    if lot.unit == "piece" and payload.quantity != payload.quantity.to_integral_value():
        raise HTTPException(422, "Piece quantities must be whole numbers")
    data = payload.model_dump()
    data.update(from_warehouse_id=None, to_warehouse_id=None)
    for side in ("from", "to"):
        location_id = data[f"{side}_location_id"]
        if location_id:
            data[f"{side}_warehouse_id"] = location(db, ctx, location_id).warehouse_id
    if payload.kind in ("release", "fulfill"):
        reservation = record(db, m.StockReservation, ctx, payload.reservation_id)
        if reservation.lot_id != lot.id:
            raise HTTPException(422, "Reservation belongs to another lot")
        location(db, ctx, reservation.location_id)
        data.update(
            from_warehouse_id=reservation.warehouse_id, from_location_id=reservation.location_id
        )
    if payload.kind == "reversal":
        original = record(db, m.StockDraft, ctx, payload.reverses_id)
        if original.lot_id != lot.id or original.status != "posted" or original.kind == "reversal":
            raise HTTPException(422, "Reversal requires an original posting in this lot")
        if payload.quantity != original.quantity:
            raise HTTPException(422, "Only full reversals are supported")
        for side in ("from", "to"):
            data[f"{side}_warehouse_id"] = getattr(original, f"{side}_warehouse_id")
            data[f"{side}_location_id"] = getattr(original, f"{side}_location_id")
    return data


def position(db, ctx, lot_id, warehouse_id, location_id, at):
    entry = m.StockEntry
    reservation = m.StockReservation
    active_reserved = case((reservation.expires_at > at, entry.reserved_delta), else_=ZERO)
    values = db.execute(
        select(
            func.coalesce(func.sum(entry.on_hand_delta), ZERO),
            func.coalesce(func.sum(entry.blocked_delta), ZERO),
            func.coalesce(func.sum(active_reserved), ZERO),
        )
        .outerjoin(
            reservation,
            and_(
                reservation.id == entry.reservation_id,
                reservation.organization_id == entry.organization_id,
            ),
        )
        .where(
            entry.organization_id == ctx.organization_id,
            entry.lot_id == lot_id,
            entry.warehouse_id == warehouse_id,
            entry.location_id == location_id,
        )
    ).one()
    return tuple(Decimal(v) for v in values)


def reservation_remaining(db, ctx, reservation_id):
    return db.scalar(
        select(func.coalesce(func.sum(m.StockEntry.reserved_delta), ZERO)).where(
            m.StockEntry.organization_id == ctx.organization_id,
            m.StockEntry.reservation_id == reservation_id,
        )
    )


def effects(db, ctx, draft, at):
    q = draft.quantity

    def leg(side, hand=ZERO, blocked=ZERO, reserved=ZERO, reservation_id=None):
        return dict(
            warehouse_id=getattr(draft, f"{side}_warehouse_id"),
            location_id=getattr(draft, f"{side}_location_id"),
            on_hand_delta=hand,
            blocked_delta=blocked,
            reserved_delta=reserved,
            reservation_id=reservation_id,
        )

    if draft.kind == "receipt":
        return [leg("to", hand=q)]
    if draft.kind == "dispatch":
        return [leg("from", hand=-q)]
    if draft.kind == "transfer":
        return [leg("from", hand=-q), leg("to", hand=q)]
    if draft.kind == "block":
        return [leg("from", blocked=q)]
    if draft.kind == "unblock":
        return [leg("from", blocked=-q)]
    if draft.kind == "reserve":
        if draft.expires_at <= at:
            raise HTTPException(409, "Reservation expired before posting")
        reservation = m.StockReservation(
            organization_id=ctx.organization_id,
            lot_id=draft.lot_id,
            warehouse_id=draft.from_warehouse_id,
            location_id=draft.from_location_id,
            quantity=q,
            expires_at=draft.expires_at,
            reference=draft.reference,
        )
        db.add(reservation)
        db.flush()
        draft.reservation_id = reservation.id
        return [leg("from", reserved=q, reservation_id=reservation.id)]
    if draft.kind in ("release", "fulfill"):
        reservation = record(db, m.StockReservation, ctx, draft.reservation_id)
        if draft.kind == "fulfill" and reservation.expires_at <= at:
            raise HTTPException(409, "Expired reservation cannot be fulfilled")
        if reservation_remaining(db, ctx, reservation.id) < q:
            raise HTTPException(409, "Quantity exceeds remaining reservation")
        return [
            leg(
                "from",
                hand=-q if draft.kind == "fulfill" else ZERO,
                reserved=-q,
                reservation_id=reservation.id,
            )
        ]
    original = record(db, m.StockDraft, ctx, draft.reverses_id)
    if original.status != "posted" or original.kind == "reversal" or original.quantity != q:
        raise HTTPException(409, "Invalid reversal target")
    if db.scalar(
        scoped(m.StockDraft, ctx).where(
            m.StockDraft.reverses_id == original.id, m.StockDraft.status == "posted"
        )
    ):
        raise HTTPException(409, "Movement already reversed")
    rows = db.scalars(scoped(m.StockEntry, ctx).where(m.StockEntry.draft_id == original.id)).all()
    return [
        dict(
            warehouse_id=e.warehouse_id,
            location_id=e.location_id,
            on_hand_delta=-e.on_hand_delta,
            blocked_delta=-e.blocked_delta,
            reserved_delta=-e.reserved_delta,
            reservation_id=e.reservation_id,
        )
        for e in rows
    ]


def validate_effects(db, ctx, lot, legs, at):
    reservation_changes = {}
    for leg in legs:
        hand, blocked, reserved = position(
            db, ctx, lot.id, leg["warehouse_id"], leg["location_id"], at
        )
        hand += leg["on_hand_delta"]
        blocked += leg["blocked_delta"]
        reserved_delta = leg["reserved_delta"]
        if leg["reservation_id"]:
            reservation = record(db, m.StockReservation, ctx, leg["reservation_id"])
            reservation_changes[reservation.id] = (
                reservation_changes.get(reservation.id, ZERO) + reserved_delta
            )
            if reservation.expires_at <= at:
                reserved_delta = ZERO
        reserved += reserved_delta
        if (
            hand < ZERO
            or hand > MAX_QUANTITY
            or blocked < ZERO
            or reserved < ZERO
            or hand < blocked + reserved
        ):
            raise HTTPException(409, "Insufficient available stock or invalid resulting position")
    for reservation_id, delta in reservation_changes.items():
        reservation = record(db, m.StockReservation, ctx, reservation_id)
        remaining = reservation_remaining(db, ctx, reservation_id) + delta
        if remaining < ZERO or remaining > reservation.quantity:
            raise HTTPException(409, "Invalid resulting reservation quantity")


def post(db, ctx, draft_id):
    candidate = record(db, m.StockDraft, ctx, draft_id)
    # One lot lock serializes all its positions/reservations, including two warehouses.
    lot = record(db, m.StockLot, ctx, candidate.lot_id, lock=True)
    draft = record(db, m.StockDraft, ctx, draft_id, lock=True)
    if draft.status == "posted":
        return draft
    if draft.status != "draft":
        raise HTTPException(409, "Rejected draft cannot be posted")
    active_lot(db, ctx, lot)
    for side in ("from", "to"):
        loc_id = getattr(draft, f"{side}_location_id")
        if loc_id:
            location(db, ctx, loc_id)
    at = now(db)
    with db.no_autoflush:
        legs = effects(db, ctx, draft, at)
        if not legs:
            raise HTTPException(409, "Posting has no ledger effects")
        validate_effects(db, ctx, lot, legs, at)
    draft.status, draft.posted_by, draft.posted_at = "posted", ctx.user_id, at
    db.flush()  # The entry trigger requires this same transaction's posted draft.
    db.add_all(
        [
            m.StockEntry(
                organization_id=ctx.organization_id, lot_id=lot.id, draft_id=draft.id, **leg
            )
            for leg in legs
        ]
    )
    db.flush()
    audit(db, ctx, "inventory_post", "inventory-drafts", draft.id)
    return draft
