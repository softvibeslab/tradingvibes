"""Manifests must survive failures without exposing credentials or mixing runs."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from tradingagents.runs import analysis_run, current_run, manifest as module, safe_settings


@pytest.fixture(autouse=True)
def lightweight_provenance(monkeypatch):
    monkeypatch.setattr(module, "source_metadata", lambda: {"commit": "test", "dirty": False})
    monkeypatch.setattr(module, "distributions", lambda: [])


def read_manifest(root, run_id):
    return json.loads((root / "runs" / run_id / "manifest.json").read_text())


def test_completed_manifest_and_secret_allowlist(tmp_path):
    config = {"results_dir": str(tmp_path), "api_key": "do-not-save",
              "backend_url": "https://user:secret@host", "temperature": 0.2,
              "data_vendors": {"core_stock_apis": "yfinance", "secret": "do-not-save"}}
    with analysis_run(config, "AAPL", "2026-01-02", ["market"]) as run:
        assert read_manifest(tmp_path, run["run_id"])["status"] == "running"
        assert current_run() is run
    saved = read_manifest(tmp_path, run["run_id"])
    assert saved["status"] == "completed"
    assert saved["finished_at"] >= saved["started_at"]
    assert saved["settings"]["temperature"] == 0.2
    assert "secret" not in json.dumps(saved) and "do-not-save" not in json.dumps(saved)
    assert current_run() is None


@pytest.mark.parametrize("error,status", [(RuntimeError("secret-url"), "failed"),
                                         (KeyboardInterrupt(), "cancelled")])
def test_failure_is_recorded_and_original_exception_preserved(tmp_path, error, status):
    with pytest.raises(type(error)) as caught, analysis_run(
        {"results_dir": str(tmp_path)}, "AAPL", "2026-01-02", []
    ) as run:
        raise error
    assert caught.value is error
    saved = read_manifest(tmp_path, run["run_id"])
    assert saved["status"] == status
    assert saved["error_type"] == type(error).__name__
    assert "secret-url" not in json.dumps(saved)
    assert current_run() is None


def test_parallel_and_nested_runs_are_isolated(tmp_path):
    barrier = Barrier(2)

    def execute(symbol):
        with analysis_run({"results_dir": str(tmp_path)}, symbol, "2026-01-02", []) as outer:
            barrier.wait(timeout=5)
            assert current_run()["ticker"] == symbol
            with analysis_run({"results_dir": str(tmp_path)}, "nested", "2026-01-02", []):
                assert current_run()["ticker"] == "nested"
            assert current_run() is outer
        return outer["run_id"]

    with ThreadPoolExecutor(2) as pool:
        ids = list(pool.map(execute, ["AAPL", "MSFT"]))
    assert len(set(ids)) == 2
    assert {read_manifest(tmp_path, i)["ticker"] for i in ids} == {"AAPL", "MSFT"}
    assert not list(tmp_path.rglob("*.tmp"))


def test_failure_to_finalize_does_not_mask_analysis_failure(tmp_path, monkeypatch):
    original = module._write

    def cannot_finalize(path, manifest):
        if manifest["status"] != "running":
            raise PermissionError("unwritable")
        original(path, manifest)

    monkeypatch.setattr(module, "_write", cannot_finalize)
    with pytest.raises(ValueError, match="analysis failed"), analysis_run(
        {"results_dir": str(tmp_path)}, "AAPL", "2026-01-02", []
    ):
        raise ValueError("analysis failed")
    assert current_run() is None


def test_settings_copy_rejects_endpoints():
    cfg = {"tool_vendors": {"get_news": "https://user:password@host"}}
    assert safe_settings(cfg)["tool_vendors"]["get_news"] is None
    assert cfg["tool_vendors"]["get_news"].startswith("https://")


def test_api_attempt_tracks_failure_without_llm(tmp_path):
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    graph = object.__new__(TradingAgentsGraph)
    graph.config = {"results_dir": str(tmp_path), "checkpoint_enabled": False}
    graph.selected_analysts = ["market"]
    graph._checkpointer_ctx = None

    def fail(*args, **kwargs):
        assert current_run()["ticker"] == "AAPL"
        raise RuntimeError("private provider response")

    graph._run_graph = fail
    with pytest.raises(RuntimeError, match="private provider response"):
        graph.propagate("AAPL", "2025-01-02")
    saved = json.loads(next(tmp_path.glob("runs/*/manifest.json")).read_text())
    assert saved["status"] == "failed"
    assert saved["analysts"] == ["market"]
    assert "private provider" not in json.dumps(saved)


def test_recorded_decision_links_run_and_restored_memory(tmp_path):
    import hashlib

    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.reporting import write_report_tree

    graph = object.__new__(TradingAgentsGraph)
    graph._log_state = lambda *args: None
    # No decision text: exercises metadata linkage without memory persistence.
    state = {"past_context": "checkpoint memory", "market_report": "verified"}
    with analysis_run({"results_dir": str(tmp_path)}, "AAPL", "2025-01-02", []) as run:
        run["initial_memory_context_sha256"] = "different-prepared-memory"
        graph.record_decision("AAPL", "2025-01-02", state)
    saved = read_manifest(tmp_path, state["run_id"])
    assert saved["memory_context_sha256"] == hashlib.sha256(b"checkpoint memory").hexdigest()
    report = write_report_tree(state, "AAPL", tmp_path / "report")
    assert state["run_id"] in report.read_text()
