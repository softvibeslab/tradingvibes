"""Explicit archive/replay bridge for normalized daily price history."""
from dataclasses import asdict
from datetime import date, datetime

from tradingagents.dataflows.prices import PriceBar, PriceHistory
from tradingagents.evidence.store import EvidenceStore


def archive_prices(store: EvidenceStore, history: PriceHistory, *, run_id: str,
                   purpose: str = "analysis") -> str:
    """Archive permitted normalized prices; the caller selects the run and purpose."""
    payload = asdict(history)
    for field in ("start", "end", "retrieved_at", "cutoff_at"):
        if payload[field] is not None:
            payload[field] = payload[field].isoformat()
    payload["bars"] = [{**bar, "session": bar["session"].isoformat()} for bar in payload["bars"]]
    return store.put(run_id=run_id, tool="daily_price_history", payload=payload, purpose=purpose)


def replay_prices(store: EvidenceStore, evidence_id: str, *, purpose: str = "analysis") -> PriceHistory:
    """Reconstruct the exact stored normalized history without any provider request."""
    record = store.get(evidence_id, purpose=purpose)
    if record["tool"] != "daily_price_history":
        raise ValueError("evidence is not a daily price history")
    payload = record["payload"]
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported price schema")
    for field in ("start", "end"):
        payload[field] = date.fromisoformat(payload[field])
    for field in ("retrieved_at", "cutoff_at"):
        if payload[field] is not None:
            payload[field] = datetime.fromisoformat(payload[field])
    payload["bars"] = tuple(
        PriceBar(**{**bar, "session": date.fromisoformat(bar["session"])}) for bar in payload["bars"]
    )
    return PriceHistory(**payload)
