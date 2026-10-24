"""Deterministic explicit dimensions; an LLM must not silently omit numeric constraints."""

import re
from dataclasses import dataclass

from app.modules.catalog_search import DIGITS, SearchDimension
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
UNIT = r"میلی[\s‌-]*متر|سانتی[\s‌-]*متر|متر|mm|cm|m"
KEY = re.compile(r"(?<!\w)(?:" + "|".join(NAMES) + r")(?=$|[\s‌:=0-9+-])", re.I)
VALUE = re.compile(
    r"[\s‌]*(?:[:=][\s‌]*)?(?P<value>" + NUMBER + r")[\s‌]*(?P<unit>" + UNIT + r")(?![\w‌])", re.I
)
MEASUREMENT = re.compile(
    NUMBER + r"[\s‌]*(?:" + UNIT + r"|میل|kg|کیلوگرم|کیلو|گرم|tonne|تن|inch|اینچ|درجه)(?![\w‌])", re.I
)

ATTEMPT = re.compile(
    r"[\s‌]*(?:[:=+0-9.٫-]|(?:از|بین|حداکثر|حداقل|یک|دو|سه|چهار|پنج|شش|هفت|هشت|نه|ده|نیم|بیست|سی|چهل|صد|one|two|three)(?=$|[\s‌]))",
    re.I,
)


@dataclass
class Extraction:
    question: str
    attributes: dict[str, SearchDimension]
    needs_clarification: bool


def extract(question):
    text = question.translate(DIGITS)
    attributes, spans = {}, []
    ambiguous = False
    for key in KEY.finditer(text):
        value = VALUE.match(text, key.end())
        name = NAMES[key.group().lower()]
        if value is None:
            # A general question about available dimensions does not assert a numeric filter.
            if ATTEMPT.match(text, key.end()):
                ambiguous = True
            continue
        if name in attributes:
            ambiguous = True
            continue
        unit = re.sub(r"[\s‌-]", "", value["unit"]).lower()
        unit = {"میلیمتر": "mm", "سانتیمتر": "cm", "متر": "m"}.get(unit, unit)
        try:
            attributes[name] = SearchDimension(value=value["value"], unit=unit)
        except ValidationError:
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
