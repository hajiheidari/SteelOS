"""Internal, non-binding sales drafts. No tax, accounting or inventory posting."""

from decimal import Decimal, localcontext

from app import models as m
from app.modules.resources import audit, get_row, scoped, serialize
from fastapi import HTTPException
from sqlalchemy import delete, func, select


def now(db):
    return db.scalar(select(func.clock_timestamp()))


def record(db, ctx, draft_id, *, lock=False):
    stmt = scoped(m.SalesDraft, ctx).where(m.SalesDraft.id == draft_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(stmt)
    if not row:
        raise HTTPException(404, "Sales draft not found")
    return row


def estimate(quantity, price):
    # 20,3 quantities × 24,6 unit prices, up to 100 lines: no default-context rounding.
    with localcontext() as ctx:
        ctx.prec = 60
        return quantity * price


def invoice_policy(currency):
    """Founder-confirmed domestic policy; compatibility never grants issuance."""
    return {
        "version": "iran-invoice-v1",
        "currency": "IRR",
        "rounding": "none",
        "currency_matches": currency == "IRR",
        "tax_workflow": "not_configured",
    }


def prepare(db, ctx, payload):
    customer = get_row(db, m.Party, ctx, payload.customer_id, shared_lock=True)
    if not customer.active or "customer" not in customer.roles:
        raise HTTPException(409, "An active customer party is required")
    prices = {
        key: get_row(db, m.PriceObservation, ctx, key, shared_lock=True)
        for key in sorted({line.price_id for line in payload.lines})
    }
    sources = {
        key: get_row(db, m.PriceSource, ctx, key, shared_lock=True)
        for key in sorted({price.source_id for price in prices.values()})
    }
    products = {
        key: get_row(db, m.Product, ctx, key, shared_lock=True)
        for key in sorted({price.product_id for price in prices.values()})
    }
    at = now(db)
    lines = []
    for index, value in enumerate(payload.lines, 1):
        price = prices[value.price_id]
        source, product = sources[price.source_id], products[price.product_id]
        if (
            price.status != "approved"
            or not source.approved
            or price.observed_at > at
            or price.valid_until <= at
        ):
            raise HTTPException(409, "A currently approved and valid price is required")
        if not product.active:
            raise HTTPException(409, "Sales product is inactive")
        if price.currency != payload.currency:
            raise HTTPException(422, "All draft prices must use the draft currency")
        if price.unit == "piece" and value.quantity != value.quantity.to_integral_value():
            raise HTTPException(422, "Piece quantities must be whole numbers")
        lines.append(
            dict(
                position=index,
                product_id=price.product_id,
                price_id=price.id,
                source_id=source.id,
                quantity=value.quantity,
                unit_price=price.amount,
                unit=price.unit,
                price_valid_until=price.valid_until,
                snapshot={
                    "product": {
                        "sku": product.sku,
                        "name": product.name,
                        "specification_hash": product.specification_hash,
                        "attributes": product.attributes,
                    },
                    "price": serialize(price),
                    "source": {
                        "name": source.name,
                        "kind": source.kind,
                        "provenance": source.provenance,
                    },
                },
            )
        )
    return lines, at


def rows_by_id(db, ctx, model, ids):
    return (
        {row.id: row for row in db.scalars(scoped(model, ctx).where(model.id.in_(ids)))}
        if ids
        else {}
    )


def details(db, ctx, draft):
    result = serialize(draft)
    customer = get_row(db, m.Party, ctx, draft.customer_id)
    result["customer_name"] = customer.name
    result["customer_eligible"] = customer.active and "customer" in customer.roles
    rows = db.scalars(
        scoped(m.SalesDraftLine, ctx)
        .where(m.SalesDraftLine.draft_id == draft.id)
        .order_by(m.SalesDraftLine.position)
    ).all()
    prices = rows_by_id(db, ctx, m.PriceObservation, {row.price_id for row in rows})
    sources = rows_by_id(db, ctx, m.PriceSource, {row.source_id for row in rows})
    products = rows_by_id(db, ctx, m.Product, {row.product_id for row in rows})
    at = now(db)
    lines = []
    with localcontext() as decimal_ctx:
        decimal_ctx.prec = 60
        total = Decimal("0")
        for row in rows:
            price, source, product = (
                prices[row.price_id],
                sources[row.source_id],
                products[row.product_id],
            )
            amount = estimate(row.quantity, row.unit_price)
            total += amount
            item = serialize(row)
            item["estimated_amount"] = format(amount, ".9f")
            item["price_usable"] = bool(
                price.status == "approved"
                and source.approved
                and product.active
                and price.observed_at <= at < price.valid_until
                and price.amount == row.unit_price
                and price.currency == draft.currency
                and price.unit == row.unit
                and product.specification_hash == row.snapshot["product"]["specification_hash"]
            )
            lines.append(item)
        result["estimated_total"] = format(total, ".9f")
    result.update(
        lines=lines,
        price_checks_as_of=at.isoformat(),
        prices_usable=all(line["price_usable"] for line in lines),
        financial_approval=False,
        invoice_policy=invoice_policy(draft.currency),
    )
    return result


def revise(db, ctx, draft, action):
    db.flush()
    response = details(db, ctx, draft)
    db.add(
        m.SalesDraftRevision(
            organization_id=ctx.organization_id,
            draft_id=draft.id,
            version=draft.version,
            actor_id=ctx.user_id,
            snapshot=response,
        )
    )
    audit(db, ctx, action, "sales-drafts", draft.id)
    return response


def change(db, ctx, draft, expected_version):
    if draft.status != "draft":
        raise HTTPException(409, "Cancelled sales draft cannot be changed")
    if draft.version != expected_version:
        raise HTTPException(409, "Sales draft version conflict")


def replace_lines(db, ctx, draft, lines):
    db.execute(
        delete(m.SalesDraftLine).where(
            m.SalesDraftLine.organization_id == ctx.organization_id,
            m.SalesDraftLine.draft_id == draft.id,
        )
    )
    db.add_all(
        [
            m.SalesDraftLine(organization_id=ctx.organization_id, draft_id=draft.id, **line)
            for line in lines
        ]
    )
