"""Ingestion adapters return unapproved observations; never write approved prices."""

from collections.abc import Iterable
from typing import Protocol

from app.schemas import PriceInput


class PriceProvider(Protocol):
    def observations(self) -> Iterable[PriceInput]: ...


class MockPriceProvider:
    def __init__(self, fixtures: list[dict]):
        self.fixtures = fixtures

    def observations(self) -> Iterable[PriceInput]:
        for fixture in self.fixtures:
            yield PriceInput.model_validate(fixture)
