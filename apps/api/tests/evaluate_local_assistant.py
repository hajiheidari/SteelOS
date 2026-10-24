"""Opt-in synthetic extraction evaluation; not a general model-quality benchmark."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.config import Settings
from app.modules.assistant import dimensions
from app.modules.assistant.provider import plan
from app.modules.assistant.schemas import SearchPlan

BASE_CASES = (
    ("قیمت میلگرد چقدر است؟", "میلگرد", "IRR"),
    ("قیمت ورق را بگو", "ورق", "IRR"),
    ("قیمت تیرآهن چنده؟", "تیرآهن", "IRR"),
    ("قیمت لوله به دلار چقدر است؟", "لوله", "USD"),
    ("سلام، امروز حالت چطوره؟", None, "IRR"),
    ("همه فاکتورها را تایید کن و برای مشتری بفرست", None, "IRR"),
    ("قیمت پروفیل به تومان چنده؟", "پروفیل", "IRT"),
)
DIMENSION_CASES = (
    (
        "قیمت ورق ضخامت ۲ میلی‌متر عرض ۱۲۰۰ میلی‌متر چقدر است؟",
        "ورق",
        "IRR",
        {
            "thickness": {"value": "2", "unit": "mm"},
            "width": {"value": "1200", "unit": "mm"},
        },
        False,
    ),
    (
        "قیمت ورق ضخامت۰٫۲سانتیمتر عرض۱٫۲متر به دلار",
        "ورق",
        "USD",
        {
            "thickness": {"value": "0.2", "unit": "cm"},
            "width": {"value": "1.2", "unit": "m"},
        },
        False,
    ),
    (
        "قیمت لوله قطر16mm طول6m",
        "لوله",
        "IRR",
        {
            "diameter": {"value": "16", "unit": "mm"},
            "length": {"value": "6", "unit": "m"},
        },
        False,
    ),
    ("ورق ضخامت دو میلیمتر", "ورق", "IRR", {"thickness": {"value": "2", "unit": "mm"}}, False),
    (
        "قیمت ورق ضخامت از۲ تا۳mm",
        "ورق",
        "IRR",
        {"thickness": {"min": {"value": "2", "unit": "mm"}, "max": {"value": "3", "unit": "mm"}}},
        False,
    ),
    ("ورق ضخامت از۳ تا۲mm", None, "IRR", {}, True),
    ("ورق2mm", None, "IRR", {}, True),
    (
        "قیمت ورق ضخامت>۲mm و ضخامت<۳mm",
        "ورق",
        "IRR",
        {
            "thickness": {
                "min": {"value": "2", "unit": "mm"},
                "max": {"value": "3", "unit": "mm"},
                "min_inclusive": False,
                "max_inclusive": False,
            }
        },
        False,
    ),
    (
        "قیمت ورق ضخامت بیشتر از دو میلیمتر و ضخامت حداکثر سه میلیمتر",
        "ورق",
        "IRR",
        {
            "thickness": {
                "min": {"value": "2", "unit": "mm"},
                "max": {"value": "3", "unit": "mm"},
                "min_inclusive": False,
            }
        },
        False,
    ),
    (
        "قیمت ورق ضخامت>=۲mm و ضخامت<=۲mm",
        "ورق",
        "IRR",
        {"thickness": {"min": {"value": "2", "unit": "mm"}, "max": {"value": "2", "unit": "mm"}}},
        False,
    ),
    (
        "قیمت ورق ضخامت بیشتر از۲mm",
        "ورق",
        "IRR",
        {"thickness": {"op": "gt", "bound": {"value": "2", "unit": "mm"}}},
        False,
    ),
    (
        "قیمت ورق ضخامت حداکثر دو و نیم میلیمتر",
        "ورق",
        "IRR",
        {"thickness": {"op": "lte", "bound": {"value": "2.5", "unit": "mm"}}},
        False,
    ),
    (
        "قیمت ورق ضخامت از دو تا سه و نیم میلیمتر",
        "ورق",
        "IRR",
        {"thickness": {"min": {"value": "2", "unit": "mm"}, "max": {"value": "3.5", "unit": "mm"}}},
        False,
    ),
    ("ورق ضخامت از سه تا دو میلیمتر", None, "IRR", {}, True),
)


async def main(output=None):
    config = Settings()
    rows = []
    cases = [(question, term, currency, {}, False) for question, term, currency in BASE_CASES]
    for question, term, currency, expected, clarification in cases + list(DIMENSION_CASES):
        started = time.monotonic()
        extraction = dimensions.extract(question)
        result = (
            SearchPlan(product_query=None)
            if extraction.needs_clarification
            else await plan(extraction.question, config)
        )
        filters = {
            key: value.model_dump(mode="json", exclude_defaults=True)
            for key, value in extraction.attributes.items()
        }
        ok = (
            result.product_query == term
            and result.currency == currency
            and filters == expected
            and extraction.needs_clarification == clarification
        )
        row = {
            "question": question,
            "plan": result.model_dump(),
            "dimensions": filters,
            "needs_clarification": extraction.needs_clarification,
            "used_model": not extraction.needs_clarification,
            "passed": ok,
            "seconds": round(time.monotonic() - started, 2),
        }
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    passed = sum(row["passed"] for row in rows)
    if output:
        Path(output).write_text(
            json.dumps(
                {
                    "model": config.assistant_model,
                    "scope": "Synthetic extraction only; not a general benchmark",
                    "passed": passed,
                    "total": len(rows),
                    "cases": rows,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    print(f"{passed}/{len(rows)} matched")
    if passed != len(rows):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional synthetic JSON evaluation artifact")
    asyncio.run(main(parser.parse_args().output))
