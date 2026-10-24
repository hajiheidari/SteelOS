"""Shared transaction mechanics; domain validation remains explicit below."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app import models as m
from app import schemas as s
from app.db import database
from app.modules import catalog_search
from app.security import Context, authorize_write, context, digest, permit
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

router = APIRouter()
RESOURCES = {
    "catalog-references": (m.Reference, s.ReferenceInput),
    "products": (m.Product, s.ProductInput),
    "product-identifiers": (m.ProductIdentifier, s.IdentifierInput),
    "parties": (m.Party, s.PartyInput),
    "warehouses": (m.Warehouse, s.WarehouseInput),
    "locations": (m.Location, s.LocationInput),
    "warehouse-access": (m.WarehouseAccess, s.AccessInput),
    "price-sources": (m.PriceSource, s.SourceInput),
    "price-observations": (m.PriceObservation, s.PriceInput),
}


def serialize(row):
    return jsonable_encoder(
        {c.name: getattr(row, c.name) for c in row.__table__.columns}, custom_encoder={Decimal: str}
    )


def audit(db, ctx, action, resource, resource_id):
    db.add(
        m.AuditEvent(
            organization_id=ctx.organization_id,
            actor_id=ctx.user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
        )
    )


def scoped(model, ctx):
    return select(model).where(model.organization_id == ctx.organization_id)


def warehouse_allowed(db, ctx, warehouse_id):
    if ctx.role == "admin":
        return
    if not db.scalar(
        scoped(m.WarehouseAccess, ctx)
        .where(
            m.WarehouseAccess.warehouse_id == warehouse_id, m.WarehouseAccess.user_id == ctx.user_id
        )
        .with_for_update(read=True)
    ):
        raise HTTPException(403, "Warehouse permission required")


def accessible(stmt, model, ctx):
    if ctx.role != "admin" and model in (m.Warehouse, m.Location):
        ids = select(m.WarehouseAccess.warehouse_id).where(
            m.WarehouseAccess.organization_id == ctx.organization_id,
            m.WarehouseAccess.user_id == ctx.user_id,
        )
        stmt = stmt.where((model.id if model == m.Warehouse else model.warehouse_id).in_(ids))
    return stmt


def get_row(db, model, ctx, record_id, *, lock=False, shared_lock=False):
    stmt = accessible(scoped(model, ctx), model, ctx).where(model.id == record_id)
    if lock or shared_lock:
        # Shared validation locks block master edits but allow independent stock postings.
        stmt = stmt.with_for_update(read=shared_lock, key_share=not shared_lock).execution_options(
            populate_existing=True
        )
    row = db.scalar(stmt)
    if not row:
        raise HTTPException(404, "Record not found")
    return row


def validate_domain(db, ctx, model, data, current=None):
    if model in (m.Warehouse, m.WarehouseAccess, m.PriceSource, m.Reference):
        permit(ctx, admin=True)
    if model == m.Reference and current:
        if data["kind"] != current.kind:
            raise HTTPException(422, "Reference kind is immutable")
        if current.attribute_rules != data["attribute_rules"] and db.scalar(
            scoped(m.Product, ctx).where(m.Product.category_id == current.id).limit(1)
        ):
            raise HTTPException(409, "Category rules in use cannot change")
    if model == m.Product:
        for kind in ("category", "manufacturer", "grade", "standard"):
            ref_id = data[f"{kind}_id"]
            if ref_id:
                ref = get_row(db, m.Reference, ctx, ref_id, lock=kind == "category")
                if ref.kind != kind:
                    raise HTTPException(422, "Incorrect catalog reference kind")
        category = get_row(db, m.Reference, ctx, data["category_id"])
        rules = category.attribute_rules
        attrs = data["attributes"]
        if set(attrs) - set(rules) or any(
            rule["required"] and key not in attrs for key, rule in rules.items()
        ):
            raise HTTPException(422, "Attributes must satisfy category rules")
        for key, value in attrs.items():
            if rules[key]["unit"] != value["unit"]:
                raise HTTPException(422, "Attribute unit does not match category rule")
            value["value"] = format(Decimal(value["value"]).normalize(), "f")
        specification = {
            key: str(data[key]) if data[key] else None
            for key in ("category_id", "manufacturer_id", "grade_id", "standard_id")
        }
        specification["attributes"] = attrs
        data["specification_hash"] = digest(json.dumps(specification, sort_keys=True))
        data["sku"] = data["sku"].upper()
        if current and (
            data["unit"] != current.unit or data["specification_hash"] != current.specification_hash
        ):
            if db.scalar(
                scoped(m.StockLot, ctx).where(m.StockLot.product_id == current.id).limit(1)
            ) or db.scalar(
                scoped(m.PriceObservation, ctx)
                .where(m.PriceObservation.product_id == current.id)
                .limit(1)
            ):
                raise HTTPException(
                    409, "Product technical identity is immutable once price history or lots exist"
                )
    if model == m.ProductIdentifier:
        get_row(db, m.Product, ctx, data["product_id"])
    if model == m.WarehouseAccess:
        get_row(db, m.Warehouse, ctx, data["warehouse_id"])
        if not db.scalar(scoped(m.Membership, ctx).where(m.Membership.user_id == data["user_id"])):
            raise HTTPException(404, "Member not found")
    if model == m.Location:
        warehouse = get_row(db, m.Warehouse, ctx, data["warehouse_id"])
        warehouse_allowed(db, ctx, warehouse.id)
        # Serialize hierarchy changes per warehouse to prevent concurrent cycles.
        db.execute(select(m.Warehouse).where(m.Warehouse.id == warehouse.id).with_for_update())
        if current and data["warehouse_id"] != current.warehouse_id:
            raise HTTPException(422, "Warehouse is immutable")
        parent_id = data["parent_id"]
        seen = {current.id} if current else set()
        while parent_id:
            if parent_id in seen:
                raise HTTPException(422, "Location hierarchy cycle")
            seen.add(parent_id)
            parent = get_row(db, m.Location, ctx, parent_id)
            if parent.warehouse_id != data["warehouse_id"]:
                raise HTTPException(422, "Parent belongs to another warehouse")
            parent_id = parent.parent_id
    if model == m.PriceObservation:
        # Serialize first price intake with technical product edits.
        get_row(db, m.Product, ctx, data["product_id"], lock=True)
        get_row(db, m.PriceSource, ctx, data["source_id"])
        if current:
            raise HTTPException(405, "Price history is immutable; create a new observation")
    return data


def page_labels(db, ctx, model, items):
    """Resolve foreign labels for this page only; never return master-list snapshots."""
    targets = (
        (m.Reference, ("category_id", "manufacturer_id", "grade_id", "standard_id")),
        (m.Product, ("product_id",)),
        (m.Warehouse, ("warehouse_id",)),
        (m.Location, ("parent_id",)),
        (m.PriceSource, ("source_id",)),
    )
    for item in items:
        item["display_names"] = {}
    for target, keys in targets:
        ids = {UUID(str(item[key])) for item in items for key in keys if item.get(key)}
        if not ids:
            continue
        related = {
            str(row.id): row
            for row in db.scalars(
                accessible(scoped(target, ctx), target, ctx).where(target.id.in_(ids))
            )
        }
        for item in items:
            for key in keys:
                row = related.get(str(item.get(key)))
                if row:
                    item["display_names"][key] = row.name
                    if model is m.Product and key == "category_id":
                        item["category_rules"] = row.attribute_rules
                    if model is m.Location and key == "warehouse_id":
                        item["warehouse_name"] = row.name
    if model is m.WarehouseAccess and items:
        ids = {UUID(str(item["user_id"])) for item in items}
        emails = dict(
            db.execute(
                select(m.User.id, m.User.email)
                .join(m.Membership, m.Membership.user_id == m.User.id)
                .where(m.Membership.organization_id == ctx.organization_id, m.User.id.in_(ids))
            ).all()
        )
        for item in items:
            item["display_names"]["user_id"] = emails.get(UUID(str(item["user_id"])))
    return items


def register(resource, model, schema):
    admin_only = model in (m.WarehouseAccess,)
    admin_write = model in (m.Warehouse, m.WarehouseAccess, m.PriceSource, m.Reference)

    def list_records(
        q: str = Query("", max_length=200),
        offset: int = Query(0, ge=0),
        limit: int = Query(25, ge=1, le=100),
        sort: str = Query("created_at"),
        direction: str = Query("desc", pattern="^(asc|desc)$"),
        category_id: UUID | None = None,
        manufacturer_id: UUID | None = None,
        grade_id: UUID | None = None,
        standard_id: UUID | None = None,
        unit: str | None = None,
        active: bool | None = None,
        kind: str | None = None,
        role: str | None = None,
        product_id: UUID | None = None,
        warehouse_id: UUID | None = None,
        status: str | None = None,
        attributes: str | None = Query(
            None,
            min_length=2,
            max_length=4096,
            description="Products only: JSON object of up to8 exact {value,unit} or inclusive {min:{value,unit},max:{value,unit}} attribute filters; AND semantics; mm/cm/m equivalence.",
        ),
        approved_only: bool = False,
        tax_included: bool | None = None,
        currency: str | None = Query(None, pattern="^(IRR|IRT|USD|EUR)$"),
        ctx: Context = Depends(context),
        db: Session = Depends(database),
    ):
        if admin_only:
            permit(ctx, admin=True)
        stmt = accessible(scoped(model, ctx), model, ctx)
        if attributes is not None:
            if model is not m.Product:
                raise HTTPException(422, "Unsupported filter: attributes")
            stmt = catalog_search.apply(stmt, model, catalog_search.parse(attributes))
        if q:
            fields = [
                getattr(model, key)
                for key in (
                    "name",
                    "code",
                    "sku",
                    "registration_id",
                    "provenance",
                    "delivery_location",
                    "delivery_terms",
                )
                if hasattr(model, key)
            ]
            if fields:
                escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                stmt = stmt.where(
                    or_(*(field.ilike(f"%{escaped}%", escape="\\") for field in fields))
                )
        for key, value in (
            ("category_id", category_id),
            ("manufacturer_id", manufacturer_id),
            ("grade_id", grade_id),
            ("standard_id", standard_id),
            ("unit", unit),
            ("active", active),
            ("kind", kind),
            ("product_id", product_id),
            ("warehouse_id", warehouse_id),
            ("status", status),
            ("currency", currency),
            ("tax_included", tax_included),
        ):
            if value is not None:
                if not hasattr(model, key):
                    raise HTTPException(422, f"Unsupported filter: {key}")
                stmt = stmt.where(getattr(model, key) == value)
        if role:
            if model != m.Party or role not in ("customer", "supplier"):
                raise HTTPException(422, "Invalid role filter")
            # JSON containment is expressed through PostgreSQL jsonb.
            from sqlalchemy import cast
            from sqlalchemy.dialects.postgresql import JSONB

            stmt = stmt.where(cast(m.Party.roles, JSONB).contains([role]))
        if approved_only:
            if model != m.PriceObservation:
                raise HTTPException(422, "Unsupported approval filter")
            now = datetime.now(UTC)
            stmt = stmt.join(
                m.PriceSource,
                (m.PriceSource.id == m.PriceObservation.source_id)
                & (m.PriceSource.organization_id == ctx.organization_id),
            ).where(
                m.PriceObservation.status == "approved",
                m.PriceObservation.valid_until > now,
                m.PriceObservation.observed_at <= now,
                m.PriceSource.approved.is_(True),
            )
        if sort not in ("created_at", "name", "code", "sku", "observed_at") or not hasattr(
            model, sort
        ):
            raise HTTPException(422, "Unsupported sort")
        count = db.scalar(select(func.count()).select_from(stmt.subquery()))
        column = getattr(model, sort)
        rows = db.scalars(
            stmt.order_by(column.asc() if direction == "asc" else column.desc(), model.id)
            .offset(offset)
            .limit(limit)
        ).all()
        items = page_labels(db, ctx, model, [serialize(row) for row in rows])
        return {
            "items": items,
            "total": count,
            "offset": offset,
            "limit": limit,
        }

    def read_record(
        record_id: UUID, ctx: Context = Depends(context), db: Session = Depends(database)
    ):
        if admin_only:
            permit(ctx, admin=True)
        return serialize(get_row(db, model, ctx, record_id))

    def create_record(
        payload,
        request: Request,
        ctx: Context = Depends(context),
        db: Session = Depends(database),
        idempotency_key: str = Header(..., min_length=1, max_length=100),
    ):
        authorize_write(db, ctx, admin=admin_write)
        fingerprint = digest(resource + json.dumps(payload.model_dump(mode="json"), sort_keys=True))
        prior = db.scalar(
            scoped(m.IdempotencyRecord, ctx).where(
                m.IdempotencyRecord.actor_id == ctx.user_id,
                m.IdempotencyRecord.key == idempotency_key,
            )
        )
        if prior:
            if prior.request_hash != fingerprint:
                raise HTTPException(409, "Idempotency key reused with different request")
            if model is m.Location:
                # Cached creation data does not confer current warehouse authority.
                row = get_row(db, model, ctx, UUID(prior.response["id"]))
                warehouse_allowed(db, ctx, row.warehouse_id)
            return prior.response
        data = payload.model_dump(mode="python")
        # Nested JSON fields contain decimal strings and no Python model instances.
        for key in ("attributes", "attribute_rules", "contacts", "addresses"):
            if key in data:
                data[key] = payload.model_dump(mode="json")[key]
        validate_domain(db, ctx, model, data)
        row = model(organization_id=ctx.organization_id, **data)
        db.add(row)
        db.flush()
        result = serialize(row)
        audit(db, ctx, "create", resource, row.id)
        db.add(
            m.IdempotencyRecord(
                organization_id=ctx.organization_id,
                actor_id=ctx.user_id,
                key=idempotency_key,
                request_hash=fingerprint,
                response=result,
            )
        )
        db.commit()
        return result

    create_record.__annotations__["payload"] = schema

    def update_record(
        record_id: UUID, payload, ctx: Context = Depends(context), db: Session = Depends(database)
    ):
        authorize_write(db, ctx, admin=admin_write)
        row = get_row(db, model, ctx, record_id, lock=model in (m.Reference, m.Product))
        data = payload.model_dump(mode="python")
        for key in ("attributes", "attribute_rules", "contacts", "addresses"):
            if key in data:
                data[key] = payload.model_dump(mode="json")[key]
        validate_domain(db, ctx, model, data, row)
        for key, value in data.items():
            setattr(row, key, value)
        audit(db, ctx, "update", resource, row.id)
        db.commit()
        return serialize(row)

    update_record.__annotations__["payload"] = schema

    def delete_record(
        record_id: UUID, ctx: Context = Depends(context), db: Session = Depends(database)
    ):
        authorize_write(db, ctx, admin=True)
        if model == m.PriceObservation:
            raise HTTPException(405, "Price history is retained")
        row = get_row(db, model, ctx, record_id)
        audit(db, ctx, "delete", resource, row.id)
        db.delete(row)
        db.commit()
        return {"deleted": True}

    for path, endpoint, method, code in (
        ("", list_records, "GET", 200),
        ("/{record_id}", read_record, "GET", 200),
        ("", create_record, "POST", 201),
        ("/{record_id}", update_record, "PUT", 200),
        ("/{record_id}", delete_record, "DELETE", 200),
    ):
        router.add_api_route(
            "/" + resource + path,
            endpoint,
            methods=[method],
            status_code=code,
            tags=[resource],
            name=f"{method}_{resource}",
        )


for name, (model, schema) in RESOURCES.items():
    register(name, model, schema)


@router.post("/price-observations/{record_id}/decision")
def decide(
    record_id: UUID,
    payload: s.Approval,
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    authorize_write(db, ctx, admin=True)
    row = get_row(db, m.PriceObservation, ctx, record_id)
    db.refresh(row, with_for_update=True)
    if row.status != "pending":
        raise HTTPException(409, "Observation already decided")
    source = get_row(db, m.PriceSource, ctx, row.source_id)
    if payload.status == "approved" and (
        not source.approved or row.valid_until <= datetime.now(UTC)
    ):
        raise HTTPException(422, "Expired price or unapproved source")
    row.status = payload.status
    audit(db, ctx, payload.status, "price-observations", row.id)
    db.commit()
    return serialize(row)


@router.get("/audit-events")
def events(
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
    ctx: Context = Depends(context),
    db: Session = Depends(database),
):
    permit(ctx, admin=True)
    stmt = scoped(m.AuditEvent, ctx)
    return {
        "items": [
            serialize(row)
            for row in db.scalars(
                stmt.order_by(m.AuditEvent.created_at.desc(), m.AuditEvent.id)
                .offset(offset)
                .limit(limit)
            )
        ],
        "total": db.scalar(select(func.count()).select_from(stmt.subquery())),
    }
