"""Replaceable signal store seam (T111).

The store interface can be replaced with Postgres/DynamoDB by implementing the same Protocol.
Callers depend on the Protocol, never on the in-memory implementation directly.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from apps.agents.risk_fraud.models import RiskSignals


@runtime_checkable
class RiskSignalStore(Protocol):
    """Protocol for loading owned risk signals by customer_id.

    Implementations:
    - InMemoryRiskSignalStore: seeded dict for PoC/test use.
    - PostgresRiskSignalStore: implements the same load_signals() against Postgres.
    - DynamoDbRiskSignalStore: implements the same load_signals() against DynamoDB.

    Callers depend on this Protocol; the concrete implementation is injected via default_store().
    """

    def load_signals(self, customer_id: str) -> RiskSignals | None:
        """Return owned risk signals for customer_id, or None if no record found."""
        ...


class InMemoryRiskSignalStore:
    """In-memory signal store backed by a pre-seeded dict (PoC/test use only)."""

    def __init__(self, records: dict[str, RiskSignals]) -> None:
        self._records = records

    def load_signals(self, customer_id: str) -> RiskSignals | None:
        return self._records.get(customer_id)


__all__ = ["RiskSignalStore", "InMemoryRiskSignalStore"]
