"""Typed company statements with explicit availability semantics.

SEC EDGAR facts are point-in-time by filing date. Yahoo/Alpha Vantage statements
date by fiscal period end without a public publication timestamp in this stack,
so historical runs must not treat them as filed evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from tradingagents.dataflows.contracts import AvailabilityBasis


@dataclass(frozen=True)
class StatementColumn:
    period_end: date
    span_label: str  # "" or " (6 months)" etc.


@dataclass(frozen=True)
class StatementRow:
    label: str
    unit: str
    cells: tuple[str, ...]  # aligned with columns; empty string = missing


@dataclass(frozen=True)
class FundamentalStatement:
    ticker: str
    kind: str
    frequency: str
    as_of_date: date
    provider: str
    title: str
    columns: tuple[StatementColumn, ...]
    rows: tuple[StatementRow, ...]
    retrieved_at: datetime
    availability_basis: AvailabilityBasis
    schema_version: int = 1

    def to_text(self) -> str:
        if self.availability_basis == "filing_date":
            vintage = (
                f"# SEC EDGAR facts filed on or before {self.as_of_date.isoformat()}, "
                f"at the values filed then\n"
            )
        else:
            vintage = (
                f"# Provider {self.provider}; availability: {self.availability_basis} "
                f"(not filing-date point-in-time)\n"
            )
        header = (
            f"# {self.title} for {self.ticker} ({self.frequency}), "
            f"USD in millions unless the row says otherwise\n"
            f"{vintage}"
            f"# retrieved_at: {self.retrieved_at.isoformat()} (not historical availability)\n\n"
        )
        col_names = [c.period_end.isoformat() + c.span_label for c in self.columns]
        lines = [",".join([""] + col_names)]
        for row in self.rows:
            name = row.label if row.unit == "USD" else f"{row.label} ({row.unit})"
            lines.append(",".join([name, *row.cells]))
        return header + "\n".join(lines) + "\n"


@dataclass(frozen=True)
class MacroObservation:
    observation_date: date
    value: str  # provider decimal text; do not round through binary float


@dataclass(frozen=True)
class MacroSeriesResult:
    """FRED (or similar) series pinneadas por vintage realtime."""

    series_id: str
    alias: str
    as_of_date: date
    vintage_date: date
    provider: str
    text: str
    retrieved_at: datetime
    availability_basis: AvailabilityBasis = "fred_realtime_vintage"
    schema_version: int = 1
    observations: tuple[MacroObservation, ...] = ()
    units: str = ""
    frequency: str = ""
    title: str = ""

    def to_text(self) -> str:
        return (
            f"# Macro {self.alias} ({self.series_id}) via {self.provider}\n"
            f"# availability: {self.availability_basis}; "
            f"realtime vintage pin: {self.vintage_date.isoformat()}; "
            f"as_of: {self.as_of_date.isoformat()}\n"
            f"# retrieved_at: {self.retrieved_at.isoformat()} (not historical availability)\n\n"
            + self.text
        )


def utc_now() -> datetime:
    return datetime.now(UTC)
