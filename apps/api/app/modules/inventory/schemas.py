from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from app.schemas import Code, Input, Text, Unit
from pydantic import Field, field_validator, model_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=3)]
Kind = Literal[
    "receipt",
    "dispatch",
    "transfer",
    "block",
    "unblock",
    "reserve",
    "release",
    "fulfill",
    "reversal",
]


class LotInput(Input):
    code: Code
    product_id: UUID
    owner_kind: Literal["company", "party"]
    owner_party_id: UUID | None = None
    unit: Unit

    @model_validator(mode="after")
    def owner(self):
        if (self.owner_kind == "party") != (self.owner_party_id is not None):
            raise ValueError("Party ownership requires exactly one explicit owner")
        return self


class DraftInput(Input):
    lot_id: UUID
    kind: Kind
    quantity: Quantity
    from_location_id: UUID | None = None
    to_location_id: UUID | None = None
    reservation_id: UUID | None = None
    reverses_id: UUID | None = None
    expires_at: datetime | None = None
    reference: Text
    note: Annotated[str, Field(max_length=1000)] = ""

    @field_validator("quantity", mode="before")
    @classmethod
    def exact_quantity(cls, value):
        if isinstance(value, (float, bool)):
            raise ValueError("Use a decimal string for inventory quantities")
        return value

    @field_validator("expires_at")
    @classmethod
    def utc(cls, value):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError("Timezone required")
            return value.astimezone(UTC)
        return value

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "receipt":
            valid = self.to_location_id and not self.from_location_id
        elif self.kind == "transfer":
            valid = (
                self.from_location_id
                and self.to_location_id
                and self.from_location_id != self.to_location_id
            )
        elif self.kind in ("dispatch", "block", "unblock", "reserve"):
            valid = self.from_location_id and not self.to_location_id
        else:
            valid = not self.from_location_id and not self.to_location_id
        if not valid:
            raise ValueError("Incorrect source/destination for this operation")
        if (self.kind in ("release", "fulfill")) != (self.reservation_id is not None):
            raise ValueError("Release/fulfillment require a reservation reference")
        if (self.kind == "reversal") != (self.reverses_id is not None):
            raise ValueError("Reversal requires an original posted movement")
        if (self.kind == "reserve") != (self.expires_at is not None):
            raise ValueError("Only reservation creation has an expiry")
        if self.expires_at is not None and self.expires_at <= datetime.now(UTC):
            raise ValueError("Reservation expiry must be in the future")
        return self
