"""Capture through real run and price boundaries, without network calls."""
import json
from datetime import datetime

import pandas as pd
import pytest

from tradingagents.dataflows import prices, router, snapshot
from tradingagents.dataflows.config import run_config
from tradingagents.evidence import EvidenceStore
from tradingagents.evidence.capture import EvidenceCaptureError
from tradingagents.evidence.prices import replay_prices
from tradingagents.memory.settlement import fetch_returns
from tradingagents.runs.manifest import analysis_run


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *a: pd.DataFrame({
        "Date": ["2026-01-05", "2026-01-06"], "Close": [100., 101.],
    }))
    return {"results_dir": str(tmp_path), "data_vendors": {"core_stock_apis": "yfinance"},
            "evidence_price_providers": ["yfinance"]}


def read_manifest(config, run):
    from pathlib import Path
    return json.loads((Path(config["results_dir"]) / "runs" / run["run_id"] / "manifest.json").read_text())


def test_tools_snapshot_and_outcomes_capture_separate_evidence(config):
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        router.route_to_vendor("get_stock_data", "AAPL", "2026-01-05", "2026-01-06")
        snapshot.build_verified_market_snapshot("AAPL", "2026-01-06")
        assert fetch_returns("AAPL", "2026-01-05", holding_days=1)[0] == pytest.approx(.01)
        saved = read_manifest(config, run)
        assert saved["status"] == "running"
        assert [r["purpose"] for r in saved["price_evidence"]] == ["analysis", "analysis", "outcome", "outcome"]
    assert read_manifest(config, run)["status"] == "completed"
    store = EvidenceStore(config["results_dir"] + "/evidence")
    for ref in run["price_evidence"]:
        assert replay_prices(store, ref["evidence_id"], purpose=ref["purpose"]).provider == "yfinance"


@pytest.mark.parametrize("providers", [[], ["alpha_vantage"]])
def test_disabled_or_unapproved_provider_is_not_archived(config, providers):
    from pathlib import Path
    config["evidence_price_providers"] = providers
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
    assert run["price_evidence"] == []
    assert not (Path(config["results_dir"]) / "evidence").exists()


def test_capture_failure_fails_run_instead_of_trying_another_vendor(config, monkeypatch):
    def refuse(*a, **k):
        raise OSError("secret-path")
    monkeypatch.setattr(EvidenceStore, "put", refuse)
    with run_config(config), pytest.raises(EvidenceCaptureError), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        router.route_to_vendor("get_stock_data", "AAPL", "2026-01-05", "2026-01-06")
    saved = read_manifest(config, run)
    assert saved["status"] == "failed"
    assert saved["error_type"] == "EvidenceCaptureError"
    assert "secret-path" not in json.dumps(saved)


def test_outcome_capture_failure_is_not_swallowed(config, monkeypatch):
    def refuse(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(EvidenceStore, "put", refuse)
    with run_config(config), pytest.raises(EvidenceCaptureError), analysis_run(config, "AAPL", "2026-01-06", []):
        fetch_returns("AAPL", "2026-01-05", holding_days=1)


def test_instant_cutoff_survives_capture_and_context_ends(config):
    config["price_calendars"] = {"AAPL": "XNYS"}
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        history = prices.get_closed_price_history("AAPL", "2026-01-05", datetime.fromisoformat("2026-01-06T22:00:00+00:00"))
    store = EvidenceStore(config["results_dir"] + "/evidence")
    assert len(run["price_evidence"]) == 1
    assert replay_prices(store, run["price_evidence"][0]["evidence_id"]) == history
    with run_config(config):
        prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
    assert len(run["price_evidence"]) == 1


def test_concurrent_calls_share_manifest_without_lost_entries(config):
    from concurrent.futures import ThreadPoolExecutor
    from contextvars import copy_context

    with (run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run,
          ThreadPoolExecutor(max_workers=4) as pool):
        futures = [pool.submit(copy_context().run, prices.get_price_history,
                               "AAPL", "2026-01-05", "2026-01-06") for _ in range(8)]
        for future in futures:
            future.result()
    saved = read_manifest(config, run)
    assert [ref["sequence"] for ref in saved["price_evidence"]] == list(range(1, 9))
    assert len(EvidenceStore(config["results_dir"] + "/evidence").for_run(run["run_id"])) == 8


def test_nested_disabled_run_does_not_inherit_capture(config):
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as outer:
        with analysis_run({**config, "evidence_price_providers": []}, "AAPL", "2026-01-06", []) as inner:
            prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
        prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
    assert inner["price_evidence"] == []
    assert len(outer["price_evidence"]) == 1


def test_cli_cutoff_and_availability_survive_integrated_router(config):
    config.update(analysis_cutoff="2026-01-06T15:00:00+00:00", price_calendars={"AAPL": "XNYS"})
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        text = router.route_to_vendor("get_stock_data", "AAPL", "2026-01-05", "2026-01-06")
    assert "from 2026-01-05 to 2026-01-05" in text
    store = EvidenceStore(config["results_dir"] + "/evidence")
    restored = replay_prices(store, run["price_evidence"][0]["evidence_id"])
    assert restored.availability_basis == "scheduled_session_close"
    assert restored.available_not_before == datetime.fromisoformat("2026-01-05T21:00:00+00:00")
    assert len(restored.bars) == 1
