"""M2 contracts only. No stock write APIs or editable balances exist in M1."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from app.schemas import Input
from pydantic import Field, model_validator

Quantity = Annotated[Decimal, Field(gt=0, max_digits=20, decimal_places=3)]


class LotContract(Input):
    id: UUID
    organization_id: UUID
    product_id: UUID
    warehouse_id: UUID
    location_id: UUID
    owner_kind: Literal["company", "party"]
    owner_party_id: UUID | None = None
    unit: Literal["kg", "tonne", "piece", "m", "m2"]

    @model_validator(mode="after")
    def legal_owner(self):
        if (self.owner_kind == "party") != (self.owner_party_id is not None):
            raise ValueError("Party ownership requires exactly one explicit owner party")
        return self


class MovementContract(Input):
    id: UUID
    organization_id: UUID
    lot_id: UUID
    quantity: Quantity
    kind: Literal["receipt", "dispatch", "transfer", "block", "unblock", "reversal"]
    occurred_at: datetime
    from_location_id: UUID | None = None
    to_location_id: UUID | None = None
    reverses_id: UUID | None = None
    idempotency_key: str

    @model_validator(mode="after")
    def movement_shape(self):
        if self.occurred_at.tzinfo is None:
            raise ValueError("Timezone required")
        if self.kind == "receipt" and (not self.to_location_id or self.from_location_id):
            raise ValueError("Receipt requires destination only")
        if self.kind == "dispatch" and (not self.from_location_id or self.to_location_id):
            raise ValueError("Dispatch requires origin only")
        if self.kind == "transfer" and (
            not self.from_location_id
            or not self.to_location_id
            or self.from_location_id == self.to_location_id
        ):
            raise ValueError("Transfer requires distinct origin and destination")
        if (self.kind == "reversal") != (self.reverses_id is not None):
            raise ValueError("Reversal must reference original movement")
        return self


class ReservationContract(Input):
    id: UUID
    organization_id: UUID
    lot_id: UUID
    quantity: Quantity
    unit: Literal["kg", "tonne", "piece", "m", "m2"]
    status: Literal["active", "released", "fulfilled", "expired"]
    expires_at: datetime
    idempotency_key: str
