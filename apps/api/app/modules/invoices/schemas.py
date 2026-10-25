from decimal import Decimal
from typing import Annotated, Literal

from app.schemas import Input
from pydantic import BeforeValidator, Field


def exact(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Use decimal strings")
    return value


Amount = Annotated[Decimal, Field(ge=0, max_digits=30, decimal_places=2), BeforeValidator(exact)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=6), BeforeValidator(exact)]
Rate = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=6), BeforeValidator(exact)]
Label = Annotated[str, Field(min_length=1, max_length=200)]


class InvoiceLine(Input):
    description: Annotated[str, Field(min_length=1, max_length=500)]
    quantity: Quantity | None = None
    unit: Annotated[str, Field(max_length=40)] | None = None
    unit_price: Rate | None = None
    line_total: Amount | None = None


class InvoiceFields(Input):
    invoice_number: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    invoice_date_text: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    seller_name: Label | None = None
    buyer_name: Label | None = None
    currency: Literal["IRR", "IRT", "USD", "EUR"] | None = None
    subtotal: Amount | None = None
    tax_total: Amount | None = None
    grand_total: Amount | None = None
    lines: list[InvoiceLine] = Field(default_factory=list, max_length=100)


class IntakeUpdate(Input):
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    corrected_text: Annotated[str, Field(max_length=100000)]
    fields: InvoiceFields
    mark_reviewed: Annotated[bool, Field(strict=True)] = False
