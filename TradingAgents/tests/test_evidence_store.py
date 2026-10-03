"""Archive integrity, concurrency, isolation and offline replay."""
from concurrent.futures import ThreadPoolExecutor

import pytest

from tradingagents.evidence import EvidenceStore


def put(store, **extra):
    return store.put(run_id="run1", tool="get_stock_data", payload={"close": 100}, **extra)


def test_deduplicates_and_links_runs(tmp_path):
    store = EvidenceStore(tmp_path)
    evidence_id = put(store)
    assert put(store) == evidence_id
    assert store.put(run_id="run2", tool="get_stock_data", payload={"close": 100}) == evidence_id
    assert len(list((tmp_path / "objects").rglob("*.json"))) == 1
    assert store.for_run("run1") == store.for_run("run2")
    assert store.get(evidence_id)["payload"] == {"close": 100}


def test_replay_is_independent_and_offline(tmp_path):
    store = EvidenceStore(tmp_path)
    evidence_id = put(store)
    store.get(evidence_id)["payload"]["close"] = 0
    assert EvidenceStore(tmp_path).get(evidence_id)["payload"]["close"] == 100
    with pytest.raises(FileNotFoundError):
        store.get("0" * 64)


def test_outcomes_cannot_enter_analysis_reads(tmp_path):
    store = EvidenceStore(tmp_path)
    evidence_id = put(store, purpose="outcome")
    with pytest.raises(ValueError, match="purpose mismatch"):
        store.get(evidence_id)
    assert store.for_run("run1") == []
    assert store.for_run("run1", purpose="outcome")[0]["payload"] == {"close": 100}


def test_corruption_is_rejected_and_not_overwritten(tmp_path):
    store = EvidenceStore(tmp_path)
    evidence_id = put(store)
    path = next((tmp_path / "objects").rglob("*.json"))
    path.write_text('{"close": 0}')
    with pytest.raises(ValueError, match="integrity"):
        store.get(evidence_id)
    with pytest.raises(ValueError, match="integrity"):
        store.for_run("run1")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        put(store)


@pytest.mark.parametrize("value", ["../escape", "/tmp/escape", "", "a/b"])
def test_unsafe_identifiers_are_rejected(tmp_path, value):
    store = EvidenceStore(tmp_path)
    with pytest.raises(ValueError):
        store.get(value)
    with pytest.raises(ValueError):
        store.put(run_id=value, tool="test", payload={})
    assert not list(tmp_path.iterdir())


def test_invalid_json_does_not_write_partial_objects(tmp_path):
    store = EvidenceStore(tmp_path)
    with pytest.raises(ValueError):
        store.put(run_id="run1", tool="test", payload={"close": float("nan")})
    assert not list(tmp_path.iterdir())


def test_concurrent_writes_do_not_lose_references(tmp_path):
    store = EvidenceStore(tmp_path)

    def write(i):
        return store.put(run_id="run1", tool="test", payload={"close": i % 4})
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(write, range(32)))
    assert len(set(ids)) == 4
    assert len(store.for_run("run1")) == 4
    assert not list(tmp_path.rglob("*.tmp"))


def test_retry_recovers_object_without_reference(tmp_path):
    store = EvidenceStore(tmp_path)
    evidence_id = put(store)
    (tmp_path / "runs" / "run1" / f"{evidence_id}.json").unlink()
    assert put(store) == evidence_id
    assert len(store.for_run("run1")) == 1


def test_typed_price_roundtrip_never_calls_provider(tmp_path, monkeypatch):
    from datetime import UTC, date, datetime

    from tradingagents.dataflows.prices import PriceBar, PriceHistory
    from tradingagents.evidence.prices import archive_prices, replay_prices

    history = PriceHistory(
        symbol="AAPL", provider_symbol="AAPL", provider="yfinance",
        start=date(2026, 1, 5), end=date(2026, 1, 6), retrieved_at=datetime(2026, 1, 7, tzinfo=UTC),
        bars=(PriceBar(date(2026, 1, 5), 101.123456), PriceBar(date(2026, 1, 6), 102.)),
        calendar_name="XNYS", cutoff_at=datetime(2026, 1, 6, 23, tzinfo=UTC),
    )

    def refuse(*args, **kwargs):
        raise AssertionError("replay must not fetch data")
    monkeypatch.setattr("tradingagents.dataflows.prices.fetch_price_frame", refuse)
    monkeypatch.setattr("tradingagents.dataflows.prices.get_stock", refuse)
    store = EvidenceStore(tmp_path)
    evidence_id = archive_prices(store, history, run_id="run1")
    assert replay_prices(store, evidence_id) == history
    outcome = archive_prices(store, history, run_id="run1", purpose="outcome")
    with pytest.raises(ValueError, match="purpose"):
        replay_prices(store, outcome)
    assert replay_prices(store, outcome, purpose="outcome") == history


@pytest.mark.parametrize("payload", [{1: "value"}, {"rows": [{2: "value"}]}, {"tuple": (1, 2)}])
def test_non_json_payloads_are_rejected_without_coercion(tmp_path, payload):
    with pytest.raises(TypeError):
        EvidenceStore(tmp_path).put(run_id="run1", tool="test", payload=payload)
    assert not list(tmp_path.iterdir())
