from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from app.schemas import Code, Input, StoredText, TaxRate
from pydantic import Field, field_validator, model_validator


class LineInput(Input):
    price_id: UUID
    quantity: Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=3)]

    @field_validator("quantity", mode="before")
    @classmethod
    def exact_quantity(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Use a decimal string for quantities")
        return value


class DraftInput(Input):
    code: Code
    customer_id: UUID
    currency: Literal["IRR", "IRT", "USD", "EUR"]
    tax_rate_percent: TaxRate | None = None
    note: Annotated[StoredText, Field(max_length=2000)] = ""
    lines: Annotated[list[LineInput], Field(min_length=1, max_length=100)]

    @model_validator(mode="after")
    def distinct_prices(self):
        if len({line.price_id for line in self.lines}) != len(self.lines):
            raise ValueError("Duplicate price lines must be combined")
        return self


class DraftUpdate(DraftInput):
    expected_version: Annotated[int, Field(ge=1, strict=True)]


class CancelInput(Input):
    expected_version: Annotated[int, Field(ge=1, strict=True)]


class ReviewInput(Input):
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    decision: Literal["accepted", "rejected"]
    note: Annotated[StoredText, Field(max_length=2000)] = ""

    @model_validator(mode="after")
    def rejection_reason(self):
        if self.decision == "rejected" and not self.note:
            raise ValueError("A rejection reason is required")
        return self
