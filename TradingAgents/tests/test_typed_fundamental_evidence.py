"""Typed provider-to-archive-to-object paths with all requests mocked."""
from datetime import date
from unittest.mock import Mock

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.vendors import fred, sec_edgar
from tradingagents.evidence import EvidenceStore
from tradingagents.evidence.fundamentals import replay_fundamental
from tradingagents.evidence.tools import replay_tools
from tradingagents.runs.manifest import analysis_run


def config(tmp_path):
    return {"results_dir": str(tmp_path),
            "data_vendors": {"fundamental_data": "sec_edgar", "macro_data": "fred"},
            "evidence_tool_providers": {"get_balance_sheet": ["sec_edgar"], "get_macro_indicators": ["fred"]}}


def test_sec_statement_survives_router_and_archive(tmp_path, monkeypatch):
    facts = {"facts": {"us-gaap": {"Assets": {"units": {"USD": [
        {"end": "2024-03-31", "val": 1e9, "filed": "2024-05-01", "form": "10-Q"},
        {"end": "2024-03-31", "val": 2e9, "filed": "2024-07-01", "form": "10-Q"},
    ]}}}}}
    monkeypatch.setattr(sec_edgar, "cik_for", lambda t: "0000320193")
    monkeypatch.setattr(sec_edgar, "_cached_json", lambda *a, **k: facts)
    cfg = config(tmp_path)
    with run_config(cfg), analysis_run(cfg, "AAPL", "2024-06-01", []) as run:
        text = router.route_to_vendor("get_balance_sheet", "AAPL", "quarterly", "2024-06-01")
    store = EvidenceStore(tmp_path / "evidence")
    evidence_id = run["tool_evidence"][0]["evidence_id"]
    monkeypatch.setattr(sec_edgar, "_cached_json", Mock(side_effect=AssertionError("no network")))
    statement = replay_fundamental(store, evidence_id)
    assert statement.to_text() == text
    assert statement.availability_basis == "filing_date"
    assert statement.columns[0].period_end == date(2024, 3, 31)
    assets = next(r for r in statement.rows if r.label == "Total Assets")
    assert assets.unit == "USD" and assets.cells == ("1000",)
    with replay_tools(store, [evidence_id]):
        assert router.route_to_vendor("get_balance_sheet", "AAPL", "quarterly", "2024-06-01") == text


def test_fred_keeps_all_points_and_decimal_strings(tmp_path, monkeypatch):
    monkeypatch.setattr(fred, "MAX_ROWS", 1)
    calls = []

    def request(path, params):
        calls.append(params)
        if path == "series":
            return {"seriess": [{"title": "Unemployment", "units_short": "%", "frequency": "Monthly"}]}
        return {"observations": [{"date": "2024-01-01", "value": "4.1234567890123456789"},
                                 {"date": "2024-02-01", "value": "."},
                                 {"date": "2024-03-01", "value": "4.20"}]}

    monkeypatch.setattr(fred, "_request", request)
    cfg = config(tmp_path)
    with run_config(cfg), analysis_run(cfg, "AAPL", "2024-06-01", []) as run:
        text = router.route_to_vendor("get_macro_indicators", "unemployment", "2024-06-01")
    store = EvidenceStore(tmp_path / "evidence")
    evidence_id = run["tool_evidence"][0]["evidence_id"]
    monkeypatch.setattr(fred, "_request", Mock(side_effect=AssertionError("no network")))
    series = replay_fundamental(store, evidence_id)
    assert series.to_text() == text
    assert "most recent 1 of 2" in text
    assert len(series.observations) == 2
    assert series.observations[0].value == "4.1234567890123456789"
    assert series.observations[1].value == "4.20"
    assert series.units == "%" and series.frequency == "Monthly"
    assert series.vintage_date == date(2024, 6, 1)
    assert series.availability_basis == "fred_realtime_vintage"
    assert all(c["realtime_start"] == c["realtime_end"] == "2024-06-01" for c in calls)
    with replay_tools(store, [evidence_id]):
        assert router.route_to_vendor("get_macro_indicators", "unemployment", "2024-06-01") == text


def test_legacy_text_is_replayable_but_not_fabricated_as_typed(tmp_path):
    store = EvidenceStore(tmp_path)
    evidence_id = store.put(run_id="run1", tool="routed_tool_response", payload={
        "schema_version": 1, "method": "get_macro_indicators", "provider": "fred",
        "args": ["cpi", "2024-06-01"], "kwargs": {}, "text": "legacy text",
    })
    with pytest.raises(ValueError, match="legacy"):
        replay_fundamental(store, evidence_id)
    with replay_tools(store, [evidence_id]):
        assert router.route_to_vendor("get_macro_indicators", "cpi", "2024-06-01") == "legacy text"


def test_typed_capture_remains_opt_in(tmp_path, monkeypatch):
    monkeypatch.setattr(fred, "_request", lambda path, params:
                        {"seriess": [{"title": "Test"}]} if path == "series" else
                        {"observations": [{"date": "2024-01-01", "value": "1"}]})
    cfg = config(tmp_path)
    cfg["evidence_tool_providers"] = {}
    with run_config(cfg), analysis_run(cfg, "AAPL", "2024-06-01", []) as run:
        text = router.route_to_vendor("get_macro_indicators", "cpi", "2024-06-01")
    assert isinstance(text, str)
    assert run["tool_evidence"] == []
    assert not (tmp_path / "evidence").exists()
