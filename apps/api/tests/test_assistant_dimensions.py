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
        "ورق عرض ازبیست تاسی میلیمتر",
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
    compared = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "ورق ضخامت بیشتر از۲mm عرض۱٫۲m"},
    ).json()
    assert [row["id"] for row in compared["products"]] == [products[1]["id"]]
    assert compared["dimensions"]["thickness"] == {
        "op": "gt",
        "bound": {"value": "2", "unit": "mm"},
    }
    assert not compared["needs_clarification"]
    combined = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "ورق ضخامت>۲mm و ضخامت<=۳mm عرض۱٫۲m"},
    ).json()
    assert [row["id"] for row in combined["products"]] == [products[1]["id"]]
    assert combined["dimensions"]["thickness"] == {
        "min": {"value": "2", "unit": "mm"},
        "max": {"value": "3", "unit": "mm"},
        "min_inclusive": False,
    }
    empty_interval = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "ورق ضخامت>۲mm و ضخامت<۳mm"},
    ).json()
    assert empty_interval["products"] == [] and not empty_interval["needs_clarification"]
    words = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "ورق ضخامت از دو تا سه میلیمتر عرض۱٫۲m"},
    ).json()
    assert {row["id"] for row in words["products"]} == {products[0]["id"], products[1]["id"]}
    assert words["dimensions"]["thickness"] == ranged["dimensions"]["thickness"]
    assert not words["needs_clarification"]
    calls.clear()
    unclear = client.post(
        "/api/v1/sales-assistant/query", headers=tokens[0], json={"question": "ورق ضخامت2"}
    ).json()
    assert unclear["needs_clarification"] and unclear["products"] == []
    assert calls == []  # No model or data lookup for ambiguous numerical intent.
    for question in (
        "ورق ضخامت بیشتر از۲",
        "ورق ضخامت۲mm نباشد",
        "ورق ضخامت از۲ تا۳mm نباشد",
        "ورق ضخامت ازدو تا سه kg",
        "ورق ضخامت>۳mm و ضخامت<۲mm",
        "ورق ضخامت>۲mm نباشد",
        "ورق ضخامت>=۲mm یا عرض۳mm",
        "ورق ضخامت از سه تا دو میلیمتر",
    ):
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
    ranged = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "قیمت ورق ضخامت از یک تا دو و نیم میلیمتر"},
    )
    assert ranged.status_code == 200, ranged.text
    ranged = ranged.json()
    assert ranged["dimensions"]["thickness"] == {
        "min": {"value": "1", "unit": "mm"},
        "max": {"value": "2.5", "unit": "mm"},
    }
    assert ranged["products"][0]["prices"][0]["id"] == price["id"]
    assert ranged["products"][0]["prices"][0]["amount"] == data["amount"]
    compared = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "قیمت ورق ضخامت حداکثر دو میلیمتر"},
    )
    assert compared.status_code == 200, compared.text
    assert compared.json()["products"][0]["prices"][0]["id"] == price["id"]
    assert compared.json()["products"][0]["prices"][0]["amount"] == data["amount"]
    no_match = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "قیمت ورق ضخامت بیشتر از۲mm"},
    )
    assert no_match.status_code == 200 and no_match.json()["products"] == []
    combined = client.post(
        "/api/v1/sales-assistant/query",
        headers=tokens[0],
        json={"question": "قیمت ورق ضخامت>=۱mm و ضخامت<۳mm"},
    )
    assert combined.status_code == 200, combined.text
    assert combined.json()["dimensions"]["thickness"]["max_inclusive"] is False
    assert combined.json()["products"][0]["prices"][0]["id"] == price["id"]
    assert combined.json()["products"][0]["prices"][0]["amount"] == data["amount"]


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
        "ورق ضخامت ≈۲mm",
        "sheet thickness above 2",
        "sheet thickness 2mm not 3mm",
        "ورق ضخامت از۲ تا۳mm نباشد",
        "ورق ضخامت به جز۲mm",
    ],
)
def test_unsupported_comparisons_never_become_equality_or_unconstrained_search(question):
    assert dimensions.extract(question).needs_clarification


@pytest.mark.parametrize(
    "question,lower,upper,lower_unit",
    [
        ("ورق ضخامت از دو تا سه میلیمتر", "2", "3", "mm"),
        ("ورق ضخامت بین دو و سه و نیم میلی‌متر", "2", "3.5", "mm"),
        ("ورق ضخامت از نیم تا دو و نیم mm", "0.5", "2.5", "mm"),
        ("ورق ضخامت از دو و نیم تا سه‌و‌نیم میلیمتر", "2.5", "3.5", "mm"),
        ("ورق ضخامت از۲ تا سه mm", "2", "3", "mm"),
        ("ورق ضخامت از نیم cm تا ده mm", "0.5", "10", "cm"),
    ],
)
def test_word_ranges_use_exact_existing_decimal_contract(question, lower, upper, lower_unit):
    from decimal import Decimal

    result = dimensions.extract(question)
    assert not result.needs_clarification and result.question == "ورق"
    interval = result.attributes["thickness"]
    assert interval.min.value == Decimal(lower) and interval.max.value == Decimal(upper)
    assert interval.min.unit == lower_unit and interval.max.unit == "mm"


@pytest.mark.parametrize(
    "question",
    [
        "ورق ضخامت از سه تا دو میلیمتر",
        "ورق ضخامت از دو و نیم تا نیم میلیمتر",
        "ورق ضخامت از نیم و نیم تا دو میلیمتر",
        "ورق ضخامت از دو تا نیم و نیم میلیمتر",
        "ورق ضخامت از دو تا سه",
        "ورق ضخامت از دو تا بیست میلیمتر",
        "ورق ضخامت ازدو تا سه kg",
        "ورق ضخامت از دو cm تا سه mm",
        "ورق ضخامت بین دو و سه میلیمتر نباشد",
    ],
)
def test_invalid_or_unsupported_word_ranges_stop_search(question):
    assert dimensions.extract(question).needs_clarification


@pytest.mark.parametrize(
    "question,op",
    [
        ("ورق ضخامت بیشتر از۲mm", "gt"),
        ("ورق ضخامت حداقل دو میلیمتر", "gte"),
        ("ورق ضخامت کمتر از۲mm", "lt"),
        ("ورق ضخامت حداکثر دو میلیمتر", "lte"),
        ("sheet thickness>2mm", "gt"),
        ("sheet thickness>=2mm", "gte"),
        ("sheet thickness<2mm", "lt"),
        ("sheet thickness<=2mm", "lte"),
        ("ورق ضخامت≥۲mm", "gte"),
        ("ورق ضخامت≤۲mm", "lte"),
    ],
)
def test_explicit_comparison_extraction(question, op):
    result = dimensions.extract(question)
    assert not result.needs_clarification
    comparison = result.attributes["thickness"]
    assert comparison.op == op and comparison.bound.value == 2 and comparison.bound.unit == "mm"
    assert result.question in ("ورق", "sheet")


@pytest.mark.parametrize(
    "question",
    [
        "ورق ضخامت>۲",
        "ورق ضخامت>دو kg",
        "ورق ضخامت>۲mm نباشد",
        "ورق ضخامت>۲mm ضخامت<۳mm",
        "ورق ضخامت>=۰mm",
        "ورق ضخامت بیشتر از سه و نیم",
        "ورق ضخامت بیشتر از بیست میلیمتر",
        "ورق ضخامت حدود۲mm",
        "ورق ضخامت>=۲mm یا عرض۳mm",
    ],
)
def test_ambiguous_comparisons_stop_before_search(question):
    assert dimensions.extract(question).needs_clarification


@pytest.mark.parametrize(
    "question,lower,upper",
    [
        ("ورق ضخامت>۲mm و ضخامت<۳mm", False, False),
        ("ورق ضخامت>=۲mm و ضخامت<۳mm", True, False),
        ("ورق ضخامت>۲mm و ضخامت<=۳mm", False, True),
        ("ورق ضخامت>=۲mm و ضخامت<=۳mm", True, True),
        ("ورق ضخامت<۳mm و ضخامت>=۲mm", True, False),
        ("ورق ضخامت بیشتر از دو میلیمتر و ضخامت حداکثر سه میلیمتر", False, True),
        ("sheet thickness>2mm and thickness<3mm", False, False),
    ],
)
def test_adjacent_opposite_comparisons_merge_only_with_explicit_conjunction(question, lower, upper):
    result = dimensions.extract(question)
    assert not result.needs_clarification and result.question in ("ورق", "sheet")
    interval = result.attributes["thickness"]
    assert interval.min.value == 2 and interval.max.value == 3
    assert interval.min_inclusive is lower and interval.max_inclusive is upper


@pytest.mark.parametrize(
    "question",
    [
        "ورق ضخامت>۳mm و ضخامت<۲mm",
        "ورق ضخامت>۲mm و ضخامت<=۲mm",
        "ورق ضخامت>=۲mm و ضخامت<۲mm",
        "ورق ضخامت>۲mm ضخامت<۳mm",
        "ورق ضخامت>۲mm یا ضخامت<۳mm",
        "ورق ضخامت>۲mm و ضخامت>۳mm",
        "ورق ضخامت<۳mm و ضخامت<۲mm",
        "ورق ضخامت>۲mm و ضخامت<۳mm و ضخامت<۴mm",
        "ورق ضخامت>۲mm و عرض۱m و ضخامت<۳mm",
        "ورق ضخامت>۲mm و ضخامت<۳mm نباشد",
        "ورق ضخامت۲mm و ضخامت<۳mm",
    ],
)
def test_unsupported_or_contradictory_combined_constraints_require_clarification(question):
    assert dimensions.extract(question).needs_clarification


def test_equal_inclusive_combined_bounds_retain_legacy_serialization():
    result = dimensions.extract("ورق ضخامت>=۲mm و ضخامت<=۲mm")
    assert not result.needs_clarification and result.question == "ورق"
    assert result.attributes["thickness"].model_dump(mode="json", exclude_defaults=True) == {
        "min": {"value": "2", "unit": "mm"},
        "max": {"value": "2", "unit": "mm"},
    }
