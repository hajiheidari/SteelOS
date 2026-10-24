"""Deterministic explicit dimensions; an LLM must not silently omit numeric constraints."""

import re
from dataclasses import dataclass
from decimal import Decimal

from app.modules.catalog_search import DIGITS, SearchDimension, SearchRange
from pydantic import ValidationError

NAMES = {
    "ضخامت": "thickness",
    "عرض": "width",
    "طول": "length",
    "قطر": "diameter",
    "ارتفاع": "height",
}
NAMES.update({name: name for name in NAMES.values()})
NUMBER = r"[0-9]+(?:٬[0-9]{3})*(?:[.٫][0-9]+)?"
WORDS = {
    "یک": "1",
    "دو": "2",
    "سه": "3",
    "چهار": "4",
    "پنج": "5",
    "شش": "6",
    "هفت": "7",
    "هشت": "8",
    "نه": "9",
    "ده": "10",
    "نیم": "0.5",
}
WORD_NUMBER = r"(?:" + "|".join(WORDS) + r")(?:[\s‌]+و[\s‌]+نیم)?"
ATOM = r"(?:" + NUMBER + "|" + WORD_NUMBER + ")"
UNIT = r"میلی[\s‌-]*متر|سانتی[\s‌-]*متر|متر|mm|cm|m"
KEY = re.compile(r"(?<!\w)(?:" + "|".join(NAMES) + r")(?=$|[\s‌:=0-9+-])", re.I)
VALUE = re.compile(
    r"[\s‌]*(?:[:=][\s‌]*)?(?P<value>"
    + NUMBER
    + "|"
    + WORD_NUMBER
    + r")[\s‌]*(?P<unit>"
    + UNIT
    + r")(?![\w‌])",
    re.I,
)
RANGE = re.compile(
    r"[\s‌]*(?:از|بین)[\s‌]*(?P<lower>"
    + ATOM
    + r")[\s‌]*(?:(?P<lower_unit>"
    + UNIT
    + r")[\s‌]*)?(?:تا|و)[\s‌]*(?P<upper>"
    + ATOM
    + r")[\s‌]*(?P<unit>"
    + UNIT
    + r")(?![\w‌])",
    re.I,
)

RANGE_START = re.compile(r"[\s‌]*(?:از|بین)[\s‌]*" + ATOM, re.I)


def decimal_value(raw):
    if raw[0] in "0123456789":
        return raw
    parts = re.split(r"[\s‌]+و[\s‌]+", raw)
    if parts[0] == "نیم" and len(parts) > 1:
        raise ValueError("Unsupported compound fraction")
    return format(
        Decimal(WORDS[parts[0]]) + (Decimal("0.5") if len(parts) > 1 else Decimal("0")), "f"
    )


def unit_code(value):
    unit = re.sub(r"[\s‌-]", "", value).lower()
    return {"میلیمتر": "mm", "سانتیمتر": "cm", "متر": "m"}.get(unit, unit)


MEASUREMENT = re.compile(
    NUMBER + r"[\s‌]*(?:" + UNIT + r"|میل|kg|کیلوگرم|کیلو|گرم|tonne|تن|inch|اینچ|درجه)(?![\w‌])", re.I
)

ATTEMPT = re.compile(
    r"[\s‌]*(?:[:=+0-9.٫-]|(?:از|بین|حداکثر|حداقل|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|نیم|بیست|سی|چهل|صد|one|two|three)(?=$|[\s‌0-9]))",
    re.I,
)


# Unsupported comparisons must not become equality or disappear before catalog search.
UNSUPPORTED_COMPARISON = re.compile(
    r"[<>≤≥≈]|(?<!\w)(?:بیشتر|بزرگتر|بزرگ‌تر|کمتر|کوچکتر|کوچک‌تر|حداقل|حداکثر|حدود|تقریباً|تقریبا|نباشد|نباشه|نیست|غیر|به[\s‌]+جز|except|not|above|below|over|under|at least|at most)(?=$|[^\w]|[0-9])",
    re.I,
)


@dataclass
class Extraction:
    question: str
    attributes: dict[str, SearchDimension | SearchRange]
    needs_clarification: bool


def extract(question):
    text = question.translate(DIGITS)
    attributes, spans = {}, []
    ambiguous = bool(KEY.search(text) and UNSUPPORTED_COMPARISON.search(text))
    for key in KEY.finditer(text):
        name = NAMES[key.group().lower()]
        interval = RANGE.match(text, key.end())
        if interval is not None:
            try:
                if name in attributes:
                    raise ValueError("Repeated dimension")
                attributes[name] = SearchRange(
                    min=SearchDimension(
                        value=decimal_value(interval["lower"]),
                        unit=unit_code(interval["lower_unit"] or interval["unit"]),
                    ),
                    max=SearchDimension(
                        value=decimal_value(interval["upper"]), unit=unit_code(interval["unit"])
                    ),
                )
                spans.append((key.start(), interval.end()))
            except (ValidationError, ValueError):
                ambiguous = True
            continue
        value = VALUE.match(text, key.end())
        if value is None:
            # A general question about available dimensions does not assert a numeric filter.
            if (
                ATTEMPT.match(text, key.end())
                or RANGE_START.match(text, key.end())
                or re.match(
                    r"[\s‌]+[آ-ی‌]+(?:[\s‌]+[آ-ی‌]+){0,4}[\s‌]*(?:" + UNIT + r")(?![\w‌])",
                    text[key.end() :],
                    re.I,
                )
            ):
                ambiguous = True
            continue
        if name in attributes:
            ambiguous = True
            continue
        unit = unit_code(value["unit"])
        try:
            attributes[name] = SearchDimension(value=decimal_value(value["value"]), unit=unit)
        except (ValidationError, ValueError):
            ambiguous = True
            continue
        spans.append((key.start(), value.end()))
    # A bare '2mm', colloquial '2میل', duplicate/missing unit or range cannot become a broad search.
    for value in MEASUREMENT.finditer(text):
        if not any(start <= value.start() and value.end() <= end for start, end in spans):
            ambiguous = True
    clean = question
    for start, end in reversed(spans):
        clean = clean[:start] + " " + clean[end:]
    clean = re.sub(r"\s+", " ", clean).strip()
    if attributes and not clean:
        ambiguous = True
    return Extraction(clean, attributes, ambiguous)
