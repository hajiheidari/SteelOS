import json
import os

import pytest
from app.modules.assistant import dimensions, provider
from app.modules.assistant.schemas import SearchPlan
from conftest import create
from test_sales_drafts import sales as sales_fixture

sales = sales_fixture


def test_explicit_dimension_extraction_is_exact_and_preserves_other_text():
    result = dimensions.extract("قیمت ورق۲ ضخامت۲ میلی‌متر عرض ۱٫۲ متر")
    assert result.question == "قیمت ورق۲" and not result.needs_clarification
    assert {key: value.model_dump(mode="json") for key, value in result.attributes.items()} == {
        "thickness": {"value": "2", "unit": "mm"},
        "width": {"value": "1.2", "unit": "m"},
    }
    general = dimensions.extract("چه ضخامت‌هایی از ورق دارید؟")
    assert not general.needs_clarification and general.attributes == {}
    english = dimensions.extract("pipe diameter:16mm length=6m")
    assert not english.needs_clarification and english.question == "pipe"
    assert english.attributes["diameter"].unit == "mm"
    assert dimensions.extract("ورق عرض۱٬۲۵۰ میلیمتر").attributes["width"].value == 1250
    assert dimensions.extract("ورق ضخامت۰٫۰۰۰۰۰۱mm").attributes["thickness"].value > 0


@pytest.mark.parametrize(
    "question",
    [
        "ورق ضخامت 2",
        "ورق ضخامت بیست میلیمتر",
        "ورق ضخامت یازده میلیمتر",
        "ورق ضخامت نیم و نیم میلیمتر",
        "ورق ضخامت دو و سه میلیمتر",
        "ورق ضخامت -2mm",
        "ورق ضخامت 0mm",
        "ورق ضخامت 0.0000001mm",
        "ورق عرض2kg",
        "ورق عرض 2inch",
        "ورق ضخامت2mm ضخامت3mm",
        "ورق عرض از1200 تا1000میلیمتر",
        "ورق عرض از1000 تا1200",
        "ورق عرض ازدو تاسه میلیمتر",
        "ورق2mm",
        "ورق2میل",
        "ورق وزن2kg",
        "ورق 2اینچ",
        "ورق عرض۲٬۵mm",
        "ضخامت2mm",
        "ورق قطر1e3mm",
    ],
)
def test_ambiguous_unsupported_or_partial_dimensions_require_clarification(question):
    assert dimensions.extract(question).needs_clarification


def test_assistant_passes_exact_filters_through_domain_api_and_never_relaxes_them(
    world, monkeypatch
):
    from app.config import settings

    client, tokens, *_ = world
    monkeypatch.setattr(settings(), "assistant_provider", "ollama")
    category = create(
        client,
        tokens[0],
        "catalog-references",
        {
            "code": "assist-dims",
            "name": "ورق",
            "kind": "category",
            "attribute_rules": {
                "thickness": {"unit": "mm", "required": True},
                "width": {"unit": "mm", "required": True},
            },
        },
    )
    products = []
    for thickness, width in (("2", "1200"), ("3", "1200"), ("2", "1000")):
        products.append(
            create(
                client,
                tokens[0],
                "products",
                {
                    "sku": f"D-{thickness}-{width}",
                    "name": "ورق",
                    "category_id": category["id"],
                    "unit": "kg",
                    "attributes": {
                        "thickness": {"value": thickness, "unit": "mm"},
                        "width": {"value": width, "unit": "mm"},
                    },
                },
            )
        )
    calls = []

    async def planner(question, config):
        calls.append(question)
        return SearchPlan(product_query="ورق")

    monkeypatch.setattr(provider, "plan", planner)
    response = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[2],
        json={"question": "قیمت ورق ضخامت۲mm عرض۱٫۲m"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert calls == ["قیمت ورق"]
    assert [row["id"] for row in result["products"]] == [products[0]["id"]]
    assert result["dimensions"]["width"] == {"value": "1.2", "unit": "m"}
    assert result["financial_approval"] is False
    assert not result["needs_clarification"]
    other = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[1],
        json={"question": "قیمت ورق ضخامت۲mm عرض۱٫۲m"},
    )
    assert other.json()["products"] == []
    empty = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "ورق ضخامت۹mm عرض۱٫۲m"},
    ).json()
    assert empty["products"] == []  # No retry dropping a constraint to get some answer.
    spelled = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "قیمت ورق ضخامت دو میلیمتر عرض۱٫۲m"},
    ).json()
    assert [row["id"] for row in spelled["products"]] == [products[0]["id"]]
    assert not spelled["needs_clarification"]
    ranged = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "ورق ضخامت از۲ تا۳mm عرض۱٫۲m"},
    ).json()
    assert {row["id"] for row in ranged["products"]} == {products[0]["id"], products[1]["id"]}
    assert ranged["dimensions"]["thickness"]["min"] == {"value": "2", "unit": "mm"}
    assert not ranged["needs_clarification"]
    calls.clear()
    unclear = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "ورق ضخامت2"}
    ).json()
    assert unclear["needs_clarification"] and unclear["products"] == []
    assert calls == []  # No model or data lookup for ambiguous numerical intent.
    for question in ("ورق ضخامت بیشتر از۲", "ورق ضخامت۲mm نباشد", "ورق ضخامت از۲ تا۳mm نباشد"):
        rejected = client.post(
            "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": question}
        ).json()
        assert rejected["needs_clarification"] and rejected["products"] == []
    assert calls == []
    assert (
        client.get(
            "/api/v1/products",
            headers=tokens[0],
            params={"attributes": json.dumps({"thickness": {"value": "2", "unit": "mm"}})},
        ).json()["total"]
        == 2
    )


@pytest.mark.skipif(
    os.environ.get("STEELOS_TEST_LOCAL_MODEL") != "1", reason="Opt-in installed local model"
)
def test_real_model_and_domain_api_preserve_exact_dimension_constraints(sales, monkeypatch):
    from app.config import settings

    client, tokens, *_rest, price, data, payload = sales
    monkeypatch.setattr(settings(), "assistant_provider", "ollama")
    response = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "قیمت ورق ضخامت۰٫۲سانتیمتر"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["dimensions"] == {"thickness": {"value": "0.2", "unit": "cm"}}
    assert result["products"][0]["attributes"]["thickness"] == {"value": "2", "unit": "mm"}
    assert result["products"][0]["prices"][0]["id"] == price["id"]
    assert result["products"][0]["prices"][0]["amount"] == data["amount"]


def test_local_model_cannot_substitute_a_generated_product_term():
    import asyncio
    from types import SimpleNamespace

    import httpx
    from fastapi import HTTPException

    config = SimpleNamespace(
        assistant_model="qwen3:1.7b", assistant_ollama_url="http://127.0.0.1:11434"
    )
    for term in ("وارق", "میلگرد"):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "message": {"content": json.dumps({"product_query": term, "currency": "IRR"})}
                },
            )
        )
        with pytest.raises(HTTPException) as error:
            asyncio.run(provider.plan("قیمت ورق چقدر است؟", config, transport=transport))
        assert error.value.status_code == 503


@pytest.mark.parametrize(
    "words,expected",
    [
        ("یک", "1"),
        ("دو", "2"),
        ("ده", "10"),
        ("نیم", "0.5"),
        ("دو و نیم", "2.5"),
        ("سه‌و‌نیم", "3.5"),
    ],
)
def test_persian_word_dimensions_are_exact(words, expected):
    from decimal import Decimal

    result = dimensions.extract(f"قیمت ورق ضخامت {words} میلی‌متر")
    assert not result.needs_clarification
    assert result.question == "قیمت ورق"
    assert result.attributes["thickness"].value == Decimal(expected)
    assert result.attributes["thickness"].unit == "mm"


@pytest.mark.parametrize(
    "question",
    ["قیمت ورق ضخامت از۲ تا۳ میلیمتر", "قیمت ورق ضخامت بین۲ و۳mm", "قیمت ورق ضخامت از۰٫۲cm تا۳mm"],
)
def test_inclusive_range_extraction(question):
    result = dimensions.extract(question)
    assert not result.needs_clarification and result.question == "قیمت ورق"
    assert result.attributes["thickness"].max.value == 3
    assert result.attributes["thickness"].max.unit == "mm"


@pytest.mark.parametrize(
    "question",
    [
        "ورق ضخامت بیشتر از۲",
        "ورق ضخامت بیشتر۲",
        "ورق ضخامت۲mm نباشد",
        "ورق ضخامت۲mm نیست",
        "ورق ضخامت حدود۲mm",
        "ورق ضخامت حداقل۲",
        "ورق ضخامت ≤۲mm",
        "sheet thickness above 2",
        "sheet thickness 2mm not 3mm",
        "ورق ضخامت از۲ تا۳mm نباشد",
        "ورق ضخامت به جز۲mm",
    ],
)
def test_unsupported_comparisons_never_become_equality_or_unconstrained_search(question):
    assert dimensions.extract(question).needs_clarification
