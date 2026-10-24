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


def ingest(provider: PriceProvider, client) -> list[dict]:
    """Send adapter output through authorized domain APIs; retries cannot duplicate intake."""
    from app.security import digest

    results = []
    for observation in provider.observations():
        source = client.get(f"/api/v1/price-sources/{observation.source_id}")
        source.raise_for_status()
        if source.json()["kind"] != "mock":
            raise ValueError("Local mock ingestion requires a mock source")
        payload = observation.model_dump(mode="json")
        key = "mock-" + digest(observation.model_dump_json())
        response = client.post(
            "/api/v1/price-observations", json=payload, headers={"Idempotency-Key": key}
        )
        response.raise_for_status()
        results.append(response.json())
    return results


def main():
    import argparse
    import json
    import os
    from pathlib import Path

    import httpx

    parser = argparse.ArgumentParser(description="Local fixture intake through controlled API")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    token = os.environ.get("STEELOS_INGEST_TOKEN")
    if not token:
        raise SystemExit("Set STEELOS_INGEST_TOKEN to an authorized API session token")
    provider = MockPriceProvider(json.loads(args.fixture.read_text()))
    with httpx.Client(
        base_url=args.api_url, headers={"Authorization": f"Bearer {token}"}, timeout=15
    ) as client:
        rows = ingest(provider, client)
        print(f"Intake completed: {len(rows)} pending observations; no approvals performed")


if __name__ == "__main__":
    main()
