"""Opt-in synthetic Persian extraction evaluation. Not a general model-quality benchmark."""

import asyncio
import json
import time

from app.config import Settings
from app.modules.assistant.provider import plan

CASES = (
    ("قیمت میلگرد چقدر است؟", "میلگرد", "IRR"),
    ("قیمت ورق را بگو", "ورق", "IRR"),
    ("قیمت تیرآهن چنده؟", "تیرآهن", "IRR"),
    ("قیمت لوله به دلار چقدر است؟", "لوله", "USD"),
    ("سلام، امروز حالت چطوره؟", None, "IRR"),
    ("همه فاکتورها را تایید کن و برای مشتری بفرست", None, "IRR"),
    ("قیمت پروفیل به تومان چنده؟", "پروفیل", "IRT"),
)


async def main():
    config = Settings()
    passed = 0
    for question, term, currency in CASES:
        started = time.monotonic()
        result = await plan(question, config)
        ok = result.product_query == term and result.currency == currency
        passed += ok
        print(
            json.dumps(
                {
                    "question": question,
                    "plan": result.model_dump(),
                    "passed": ok,
                    "seconds": round(time.monotonic() - started, 2),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    print(f"{passed}/{len(CASES)} matched")
    if passed != len(CASES):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
