"""Opt-in synthetic real-model evaluation; no business DB, tools or model downloads."""

import argparse
import asyncio
import json
import time
from pathlib import Path

from app.config import Settings
from app.modules.agent_workbench import provider


async def evaluate(path):
    config = Settings()
    cases = []
    raw_candidates = []
    original_validate = provider.validate_output

    def capture(value, sources, kind):
        raw_candidates.append(value)
        return original_validate(value, sources, kind)

    provider.validate_output = capture
    for kind in provider.TASKS:
        sources = (
            [{"alias": "S1", "content": "مالکیت کالا مستقل از محل نگهداری است."}]
            if kind in ("research", "education")
            else []
        )
        brief = {
            "research": "با استناد به یادداشت، طرح آزمایشی برای جلوگیری از اشتباه مالکیت کالا پیشنهاد بده.",
            "education": "برای کارشناس تازه‌کار یک درس کوتاه و تمرین درباره تفاوت مالکیت و محل نگهداری بساز.",
            "marketing": "فقط یک طرح اولیه برای محتوای آموزشی مخاطب صنعتی درباره انتخاب تأمین‌کننده فولاد بساز؛ قیمت و وعده نده.",
            "sales": "فقط طرح اولیه پرسش‌های کشف نیاز یک مشتری ورق و برنامه پیگیری داخلی بساز؛ قیمت و موجودی اعلام نکن.",
        }[kind]
        started = time.monotonic()
        raw_candidates.clear()
        try:
            result = await provider.generate(kind, brief, sources, config)
            cases.append(
                {"kind": kind, "passed": True, "sources": sources, "brief": brief, "output": result}
            )
        except Exception as error:
            cases.append(
                {
                    "kind": kind,
                    "passed": False,
                    "error_type": type(error).__name__,
                    "status": getattr(error, "status_code", None),
                }
            )
        cases[-1]["seconds"] = round(time.monotonic() - started, 2)
        if not cases[-1]["passed"] and raw_candidates:
            cases[-1]["unvalidated_synthetic_candidate"] = raw_candidates[-1]
        path.write_text(
            json.dumps(
                {
                    "synthetic_only": True,
                    "model": config.agent_workbench_model,
                    "policy_version": provider.POLICY_VERSION,
                    "production_benchmark": False,
                    "cases": cases,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(kind, cases[-1]["passed"], flush=True)
    if not all(case["passed"] for case in cases):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-local-model", action="store_true", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(evaluate(args.output))
