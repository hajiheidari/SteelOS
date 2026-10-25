from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[str, Field(min_length=1, max_length=200)]
Code = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")]
Unit = Literal["kg", "tonne", "piece", "m", "m2"]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def exact_tax_rate(value):
    if isinstance(value, (float, bool)):
        raise ValueError("Use a decimal string for tax rates")
    return value


TaxRate = Annotated[
    Decimal,
    Field(ge=0, le=100, max_digits=9, decimal_places=6),
    BeforeValidator(exact_tax_rate),
]


class TaxPolicyUpdate(Input):
    tax_rate_percent: TaxRate
    expected_version: Annotated[int, Field(ge=1, strict=True)]


class Login(Input):
    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[
        str, StringConstraints(strip_whitespace=False), Field(min_length=1, max_length=128)
    ]
    organization_id: UUID


class NewMember(Input):
    email: Annotated[
        str, Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    ]
    password: Annotated[
        str, StringConstraints(strip_whitespace=False), Field(min_length=12, max_length=128)
    ]
    role: Literal["admin", "editor", "viewer"]


class AttributeRule(Input):
    unit: Literal["mm", "cm", "m", "kg", "none"]
    required: bool = False


class ReferenceInput(Input):
    kind: Literal["category", "manufacturer", "grade", "standard"]
    code: Code
    name: Text
    attribute_rules: dict[Code, AttributeRule] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def rules_only_for_category(self):
        if self.kind != "category" and self.attribute_rules:
            raise ValueError("Only categories define attribute rules")
        return self


class Dimension(Input):
    value: Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=6)]
    unit: Literal["mm", "cm", "m", "kg", "none"]

    @field_validator("value", mode="before")
    @classmethod
    def no_float(cls, value):
        if isinstance(value, float):
            raise ValueError("Use decimal strings, not JSON floating point numbers")
        return value


class ProductInput(Input):
    sku: Code
    name: Text
    category_id: UUID
    manufacturer_id: UUID | None = None
    grade_id: UUID | None = None
    standard_id: UUID | None = None
    unit: Unit
    attributes: dict[Code, Dimension] = Field(default_factory=dict, max_length=50)
    active: bool = True


class IdentifierInput(Input):
    product_id: UUID
    kind: Annotated[Code, Field(max_length=30)]
    value: Annotated[str, Field(min_length=1, max_length=100)]


class Contact(Input):
    name: Text
    kind: Literal["phone", "email", "contact_person"]
    value: Text


class Address(Input):
    city: Annotated[str, Field(min_length=1, max_length=100)]
    address: Annotated[str, Field(min_length=1, max_length=1000)]
    postal_code: Annotated[str, Field(max_length=20)] = ""


class PartyInput(Input):
    name: Text
    kind: Literal["individual", "legal_entity"]
    registration_id: Annotated[str, Field(min_length=1, max_length=30)] | None = None
    roles: Annotated[list[Literal["customer", "supplier"]], Field(min_length=1, max_length=2)]
    contacts: list[Contact] = Field(default_factory=list, max_length=30)
    addresses: list[Address] = Field(default_factory=list, max_length=30)
    active: bool = True

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value):
        return sorted(set(value))


class WarehouseInput(Input):
    code: Annotated[Code, Field(max_length=40)]
    name: Text
    city: Annotated[str, Field(min_length=1, max_length=100)]
    address: Annotated[str, Field(min_length=1, max_length=1000)]
    active: bool = True


class LocationInput(Input):
    warehouse_id: UUID
    parent_id: UUID | None = None
    code: Annotated[Code, Field(max_length=40)]
    name: Text
    kind: Annotated[Code, Field(max_length=40)]


class AccessInput(Input):
    warehouse_id: UUID
    user_id: UUID


class SourceInput(Input):
    code: Code
    name: Text
    kind: Literal["manual", "mock"]
    provenance: Annotated[str, Field(min_length=1, max_length=2000)]
    approved: bool = False


class PriceInput(Input):
    product_id: UUID
    source_id: UUID
    amount: Annotated[Decimal, Field(gt=0, max_digits=24, decimal_places=6)]
    currency: Literal["IRR", "IRT", "USD", "EUR"]
    unit: Unit
    observed_at: datetime
    valid_until: datetime
    delivery_location: Annotated[str, Field(min_length=1, max_length=500)]
    delivery_terms: Annotated[str, Field(min_length=1, max_length=1000)]
    tax_included: bool
    provenance: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("amount", mode="before")
    @classmethod
    def decimal_string(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Use a decimal string for money")
        try:
            if not Decimal(value).is_finite():
                raise ValueError("Finite amount required")
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValueError("Invalid decimal") from exc
        return value

    @field_validator("observed_at", "valid_until")
    @classmethod
    def utc(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        try:
            return value.astimezone(UTC)
        except OverflowError as exc:
            raise ValueError("Date outside supported UTC range") from exc

    @model_validator(mode="after")
    def dates(self):
        if self.valid_until <= self.observed_at or self.observed_at > datetime.now(UTC):
            raise ValueError("Invalid observation interval")
        return self


class Approval(Input):
    status: Literal["approved", "rejected"]


class OrganizationUpdate(Input):
    name: Text


class PasswordUpdate(Input):
    current_password: Annotated[
        str, StringConstraints(strip_whitespace=False), Field(min_length=1, max_length=128)
    ]
    new_password: Annotated[
        str, StringConstraints(strip_whitespace=False), Field(min_length=12, max_length=128)
    ]


class RoleUpdate(Input):
    role: Literal["admin", "editor", "viewer"]


class FollowUpInput(Input):
    party_id: UUID
    name: Text
    kind: Literal["call", "meeting", "document", "other"] = "call"
    due_at: datetime
    status: Literal["open", "completed", "cancelled"] = "open"
    notes: Annotated[str, Field(max_length=1000)] = ""

    @field_validator("due_at")
    @classmethod
    def aware_utc(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        try:
            return value.astimezone(UTC)
        except OverflowError as exc:
            raise ValueError("Date outside supported UTC range") from exc
