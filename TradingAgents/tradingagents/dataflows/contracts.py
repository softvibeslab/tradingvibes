"""Shared provenance fields. Retrieval time is never historical availability."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# What justifies claiming a datum could have been known by a cutoff.
AvailabilityBasis = Literal[
    "unknown",
    "not_applicable",
    "scheduled_session_close",
    "filing_date",
    "fred_realtime_vintage",
]


@dataclass(frozen=True)
class Provenance:
    """Machine-readable origin metadata shared across typed data families.

    ``available_not_before`` is a lower bound when the basis can support one.
    It is never set from download time. ``retrieved_at`` is operational only.
    """

    provider: str
    availability_basis: AvailabilityBasis
    retrieved_at: datetime
    available_not_before: datetime | None = None
    feed: str | None = None
    market: str | None = None
    currency: str | None = None
    payload_sha256: str | None = None

    def assert_not_retrieval_as_availability(self) -> None:
        if (
            self.available_not_before is not None
            and self.available_not_before == self.retrieved_at
            and self.availability_basis != "not_applicable"
        ):
            raise ValueError(
                "available_not_before must not be copied from retrieved_at; "
                "retrieval time is not historical availability"
            )
