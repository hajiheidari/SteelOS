"""Fixed read-only tool registry. Model/user cannot choose a URL, method, tenant or limit."""

import json
from datetime import UTC, datetime

import httpx
from app.modules.assistant.schemas import SearchPlan
from fastapi import HTTPException

TOOLS = ("catalog.search", "prices.current")
PRODUCT_FIELDS = ("id", "sku", "name", "unit", "attributes")
PRICE_FIELDS = (
    "id",
    "source_id",
    "amount",
    "currency",
    "unit",
    "observed_at",
    "valid_until",
    "delivery_location",
    "delivery_terms",
    "tax_included",
    "provenance",
)


async def get(client, path, params=None):
    response = await client.get("/api/v1/" + path, params=params)
    if response.status_code in (401, 403):
        raise HTTPException(response.status_code, "Session authorization changed")
    if response.status_code != 200:
        raise HTTPException(503, "Sales domain data is temporarily unavailable")
    return response.json()


async def search(
    app, authorization, plan: SearchPlan, *, attributes=None, needs_clarification=False
):
    started = datetime.now(UTC)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://steelos.internal",
        headers={"Authorization": authorization},
        trust_env=False,
    ) as client:
        rows = []
        total = 0
        if plan.product_query and not needs_clarification:
            products = await get(
                client,
                "products",
                {
                    "q": plan.product_query,
                    "active": "true",
                    "limit": 5,
                    "offset": 0,
                    **(
                        {
                            "attributes": json.dumps(
                                {
                                    key: value.model_dump(mode="json", exclude_defaults=True)
                                    for key, value in attributes.items()
                                }
                            )
                        }
                        if attributes
                        else {}
                    ),
                },
            )
            total = products["total"]
            for product in products["items"]:
                prices = await get(
                    client,
                    "price-observations",
                    {
                        "product_id": product["id"],
                        "currency": plan.currency,
                        "approved_only": "true",
                        "sort": "observed_at",
                        "direction": "desc",
                        "limit": 5,
                        "offset": 0,
                    },
                )
                row = {field: product[field] for field in PRODUCT_FIELDS}
                row["prices"] = [
                    {
                        **{field: price[field] for field in PRICE_FIELDS},
                        "source_name": price.get("display_names", {}).get("source_id"),
                    }
                    for price in prices["items"]
                ]
                row["price_total"] = prices["total"]
                rows.append(row)
        # Recheck live session after any model delay/domain reads before returning tenant data.
        await get(client, "auth/me")
    return {
        "products": rows,
        "product_total": total,
        "query": plan.product_query,
        "dimensions": {
            key: value.model_dump(mode="json", exclude_defaults=True)
            for key, value in (attributes or {}).items()
        },
        "needs_clarification": needs_clarification,
        "currency": plan.currency,
        "retrieval_started_at": started.isoformat(),
        "retrieval_finished_at": datetime.now(UTC).isoformat(),
        "read_only": True,
        "financial_approval": False,
        "tools": list(TOOLS),
    }
