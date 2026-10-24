import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from app import models as m
from app.config import Settings
from app.db import engine
from app.modules.assistant import provider, tools
from app.modules.assistant.schemas import SearchPlan
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_sales_drafts import sales as sales_fixture

sales = sales_fixture


def enabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "assistant_provider", "ollama")


def test_assistant_default_disabled_and_authenticated(world):
    client, tokens, *_ = world
    assert client.get("/api/v1/sales-assistant/status").status_code == 401
    status = client.get("/api/v1/sales-assistant/status", headers=tokens[0]).json()
    assert status["configured"] is False and status["provider"] == "disabled"
    assert status["read_only"] and not status["financial_approval"]
    assert (
        client.post(
            "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "قیمت میلگرد"}
        ).status_code
        == 503
    )
    for extra in (
        {"organization_id": str(uuid4())},
        {"tools": ["approve"]},
        {"url": "https://example.test"},
    ):
        assert (
            client.post(
                "/api/v1/sales-assistant/query",
                headers=tokens[0],
                json={"question": "میلگرد", **extra},
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "x" * 1001}
        ).status_code
        == 422
    )


def test_assistant_tool_search_is_tenant_scoped_evidenced_and_never_writes_business_data(
    sales, monkeypatch
):
    client, tokens, orgs, *_rest, price_data, _ = sales
    enabled(monkeypatch)
    questions = []

    async def planner(question, config):
        questions.append(question)
        return SearchPlan(product_query="ورق", currency="IRR")

    monkeypatch.setattr(provider, "plan", planner)
    response = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[2], json={"question": "قیمت ورق را بگو"}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "local_model" and result["read_only"]
    assert result["financial_approval"] is False
    assert result["tools"] == ["catalog.search", "prices.current"]
    assert len(result["products"]) == 1
    price = result["products"][0]["prices"][0]
    assert price["amount"] == price_data["amount"]
    assert price["provenance"] == price_data["provenance"]
    assert price["currency"] == "IRR" and price["unit"] == "kg"
    assert "organization_id" not in price and "contacts" not in result["products"][0]
    other = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[1], json={"question": "قیمت ورق را بگو"}
    ).json()
    assert other["products"] == [] and other["product_total"] == 0
    assert questions == ["قیمت ورق را بگو", "قیمت ورق را بگو"]
    with Session(engine()) as db:
        for model in (m.SalesDraft, m.SalesDraftReview, m.StockEntry):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert (
            db.scalar(
                select(func.count())
                .select_from(m.AuditEvent)
                .where(
                    m.AuditEvent.organization_id == orgs[0],
                    m.AuditEvent.action == "assistant_query",
                )
            )
            == 1
        )


def test_assistant_filters_unapproved_expired_other_currency_and_revoked_sources(
    sales, monkeypatch
):
    from conftest import create

    client, tokens, *_rest, source, price, data, _ = sales
    enabled(monkeypatch)

    async def planner(question, config):
        return SearchPlan(product_query="ورق", currency="IRR")

    monkeypatch.setattr(provider, "plan", planner)
    create(client, tokens[0], "price-observations", data)  # pending
    create(client, tokens[0], "price-observations", {**data, "currency": "USD"})
    at = datetime.now(UTC)
    expired = create(
        client,
        tokens[0],
        "price-observations",
        {
            **data,
            "observed_at": (at - timedelta(days=2)).isoformat(),
            "valid_until": (at - timedelta(days=1)).isoformat(),
        },
    )
    with Session(engine()) as db:
        db.get(m.PriceObservation, expired["id"]).status = "approved"
        db.commit()
    path = "/api/v1/sales-assistant/query"
    result = client.post(path, headers=tokens[0], json={"question": "قیمت ورق"}).json()
    assert [row["id"] for row in result["products"][0]["prices"]] == [price["id"]]
    assert (
        client.put(
            f"/api/v1/price-sources/{source['id']}",
            headers=tokens[0],
            json={
                key: (False if key == "approved" else source[key])
                for key in ("code", "name", "kind", "provenance", "approved")
            },
        ).status_code
        == 200
    )
    assert (
        client.post(path, headers=tokens[0], json={"question": "قیمت ورق"}).json()["products"][0][
            "prices"
        ]
        == []
    )


def test_session_revoked_during_model_call_returns_no_data(sales, monkeypatch):
    client, tokens, *_ = sales
    enabled(monkeypatch)

    async def planner(question, config):
        with Session(engine()) as db:
            from app.security import digest

            row = db.scalar(
                select(m.AuthSession).where(
                    m.AuthSession.token_hash == digest(tokens[0]["Authorization"].split()[1])
                )
            )
            db.delete(row)
            db.commit()
        return SearchPlan(product_query="ورق")

    monkeypatch.setattr(provider, "plan", planner)
    result = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "ورق"}
    )
    assert result.status_code == 401
    assert "ورق دو" not in result.text and "products" not in result.json()


def test_local_provider_is_bounded_and_never_receives_token_or_business_data():
    config = SimpleNamespace(
        assistant_model="qwen3:1.7b", assistant_ollama_url="http://127.0.0.1:11434"
    )

    def handler(request):
        assert request.url.path == "/api/chat"
        assert "authorization" not in request.headers
        data = json.loads(request.content)
        assert data["options"]["num_predict"] == 256
        assert data["stream"] is False and data["think"] is False
        assert data["messages"][1] == {"role": "user", "content": "قیمت میلگرد"}
        return httpx.Response(
            200, json={"message": {"content": '{"product_query":"میلگرد","currency":"IRR"}'}}
        )

    result = asyncio.run(
        provider.plan("قیمت میلگرد", config, transport=httpx.MockTransport(handler))
    )
    assert result.product_query == "میلگرد"
    for response in (
        httpx.Response(302, headers={"Location": "https://example.test"}),
        httpx.Response(
            200,
            json={"message": {"content": '{"product_query":"میلگرد","organization_id":"secret"}'}},
        ),
        httpx.Response(200, content=b"x" * 65537),
        httpx.Response(200, json={"message": {"content": "not JSON SECRET"}}),
    ):
        with pytest.raises(HTTPException) as error:
            asyncio.run(
                provider.plan(
                    "قیمت میلگرد", config, transport=httpx.MockTransport(lambda request: response)
                )
            )
        assert error.value.status_code == 503
        assert "SECRET" not in error.value.detail


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com",
        "http://127.0.0.1@evil.test",
        "http://localhost:11434/path",
        "http://localhost:11434?token=secret",
    ],
)
def test_external_model_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        Settings(assistant_ollama_url=url, _env_file=None)


def test_tool_budget_is_fixed_and_unknown_intent_cannot_mutate(sales, monkeypatch):
    from conftest import create

    client, tokens, *_ = sales
    category = create(
        client,
        tokens[0],
        "catalog-references",
        {
            "kind": "category",
            "code": "assistant-bounded",
            "name": "گروه دستیار",
            "attribute_rules": {"variant": {"unit": "mm", "required": True}},
        },
    )
    for index in range(6):
        create(
            client,
            tokens[0],
            "products",
            {
                "sku": f"BOUND-{index}",
                "name": f"محدود {index}",
                "unit": "kg",
                "category_id": category["id"],
                "attributes": {"variant": {"value": str(index + 1), "unit": "mm"}},
            },
        )
    enabled(monkeypatch)

    async def planner(question, config):
        return SearchPlan(product_query="محدود" if question == "محدود" else None)

    monkeypatch.setattr(provider, "plan", planner)
    calls = []
    original = tools.get

    async def tracked(client, path, params=None):
        calls.append((path, params))
        return await original(client, path, params)

    monkeypatch.setattr(tools, "get", tracked)
    response = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "محدود"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["product_total"] == 6 and len(response.json()["products"]) == 5
    assert len(calls) == 7  # search +5 current-price reads + final session check
    assert all(params is None or params["limit"] == 5 for _, params in calls)
    calls.clear()
    result = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "فاکتور را تایید و ارسال کن"},
    ).json()
    assert result["products"] == [] and result["query"] is None
    assert calls == [("auth/me", None)]


def test_provider_busy_budget_returns_429_without_starting_another_call(world, monkeypatch):
    from app.modules.assistant import router

    client, tokens, *_ = world
    enabled(monkeypatch)
    monkeypatch.setattr(router, "slots", asyncio.Semaphore(0))
    response = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "میلگرد"}
    )
    assert response.status_code == 429


def test_cloud_or_arbitrary_models_cannot_be_configured():
    with pytest.raises(ValidationError):
        Settings(assistant_model="premium-cloud:latest", _env_file=None)


@pytest.mark.skipif(
    os.environ.get("STEELOS_TEST_LOCAL_MODEL") != "1",
    reason="Opt-in installed free local model evaluation",
)
def test_real_local_model_uses_actual_scoped_domain_prices(sales, monkeypatch):
    client, tokens, *_rest, price, data, _ = sales
    enabled(monkeypatch)
    # Intentionally uses the actual provider/model, with no provider monkeypatch.
    response = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "قیمت ورق را بگو"}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["query"] == "ورق"
    assert result["products"][0]["prices"][0]["id"] == price["id"]
    assert result["products"][0]["prices"][0]["amount"] == data["amount"]
    assert result["financial_approval"] is False


def test_assistant_search_terms_and_questions_are_not_written_to_logs(world, monkeypatch, caplog):
    import logging

    client, tokens, *_ = world
    enabled(monkeypatch)
    marker = "sensitive-search-marker"

    async def planner(question, config):
        return SearchPlan(product_query=marker)

    monkeypatch.setattr(provider, "plan", planner)
    caplog.set_level(logging.INFO)
    response = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": marker}
    )
    assert response.status_code == 200
    assert marker not in caplog.text


def test_provider_has_a_total_deadline_not_just_per_chunk_timeout(monkeypatch):
    monkeypatch.setattr(provider, "DEADLINE_SECONDS", 0.001)

    async def slow(request):
        await asyncio.sleep(0.02)
        return httpx.Response(200, json={"message": {"content": '{"product_query":"ورق"}'}})

    config = SimpleNamespace(
        assistant_model="qwen3:1.7b", assistant_ollama_url="http://127.0.0.1:11434"
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(provider.plan("ورق", config, transport=httpx.MockTransport(slow)))
    assert error.value.status_code == 503
