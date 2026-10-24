"""Exact, bounded, extensible product-attribute search; no price/stock conversions."""

import json
import re
from decimal import Decimal, localcontext
from typing import Annotated

from app.schemas import Code, Dimension, Input
from fastapi import HTTPException
from pydantic import Field, ValidationError, field_validator
from sqlalchemy import cast, or_
from sqlalchemy.dialects.postgresql import JSONB

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
LENGTH_FACTORS = {"mm": Decimal("0.001"), "cm": Decimal("0.01"), "m": Decimal("1")}


class SearchDimension(Dimension):
    @field_validator("value", mode="before")
    @classmethod
    def exact_value(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Use decimal strings for dimension filters")
        if isinstance(value, str):
            value = value.strip().translate(DIGITS)
            if "٬" in value and not re.fullmatch(r"[0-9]{1,3}(?:٬[0-9]{3})+(?:[.٫][0-9]+)?", value):
                raise ValueError("Invalid thousands grouping")
            return value.replace("٫", ".").replace("٬", "")
        return value


class AttributeFilters(Input):
    attributes: Annotated[dict[Code, SearchDimension], Field(max_length=8)]


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse(raw):
    try:
        value = json.loads(raw, object_pairs_hook=unique_pairs)
        filters = AttributeFilters(attributes=value).attributes
        if len(filters) != len(value):
            raise ValueError("Duplicate normalized attribute key")
        return filters
    except (ValueError, TypeError, RecursionError, ValidationError):
        raise HTTPException(422, "Invalid product attribute filters") from None


def alternatives(dimension):
    with localcontext() as context:
        context.prec = 40
        units = (
            LENGTH_FACTORS if dimension.unit in LENGTH_FACTORS else {dimension.unit: Decimal("1")}
        )
        physical = dimension.value * units[dimension.unit]
        return [
            {"value": format((physical / factor).normalize(), "f"), "unit": unit}
            for unit, factor in units.items()
        ]


def apply(stmt, model, attributes):
    for key, dimension in attributes.items():
        stmt = stmt.where(
            or_(
                *[
                    cast(model.attributes, JSONB).contains({key: candidate})
                    for candidate in alternatives(dimension)
                ]
            )
        )
    return stmt
