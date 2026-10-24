"""Bounded page projections; resolve names without downloading entire master lists."""

from uuid import UUID

from app import models as m
from app.modules.inventory import service
from app.modules.resources import accessible, scoped


def describe(db, ctx, items, *, lot_rows=False):
    def ids(keys):
        return {UUID(str(row[key])) for row in items for key in keys if row.get(key)}

    def fetch(model, keys):
        if not keys:
            return {}
        stmt = scoped(model, ctx).where(model.id.in_(keys))
        if model in (m.Warehouse, m.Location):
            stmt = accessible(stmt, model, ctx)
        elif model in (m.StockLot, m.StockDraft):
            stmt = service.visible(stmt, model, ctx)
        return {str(row.id): row for row in db.scalars(stmt)}

    lots = fetch(m.StockLot, ids(["id"] if lot_rows else ["lot_id"]))
    products = fetch(m.Product, {lot.product_id for lot in lots.values()})
    parties = fetch(m.Party, {lot.owner_party_id for lot in lots.values() if lot.owner_party_id})
    locations = fetch(m.Location, ids(["location_id", "from_location_id", "to_location_id"]))
    warehouses = fetch(m.Warehouse, {loc.warehouse_id for loc in locations.values()})
    drafts = fetch(m.StockDraft, ids(["draft_id"]))
    for item in items:
        lot = lots.get(str(item.get("id" if lot_rows else "lot_id")))
        if lot:
            product = products.get(str(lot.product_id))
            party = parties.get(str(lot.owner_party_id))
            item.update(
                lot_code=lot.code,
                product_name=product.name if product else None,
                owner_name=party.name if party else None,
                owner_kind=lot.owner_kind,
                unit=lot.unit,
            )
        for prefix in ("", "from_", "to_"):
            loc = locations.get(str(item.get(prefix + "location_id")))
            warehouse = warehouses.get(str(loc.warehouse_id)) if loc else None
            item[prefix + "location_name"] = loc.name if loc else None
            item[prefix + "warehouse_name"] = warehouse.name if warehouse else None
        if item.get("draft_id"):
            draft = drafts.get(str(item["draft_id"]))
            item["draft_reference"] = draft.reference if draft else None
    return items
