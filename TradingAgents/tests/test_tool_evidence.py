"""Exact tool response capture and fail-closed replay at the real router boundary."""
from unittest.mock import Mock

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.evidence import EvidenceStore
from tradingagents.evidence.capture import EvidenceCaptureError
from tradingagents.evidence.tools import EvidenceReplayError, replay_tools
from tradingagents.runs.manifest import analysis_run


@pytest.fixture
def setup(tmp_path, monkeypatch):
    vendor = Mock(return_value="Filed financial data: 123.456\n")
    fred = Mock(return_value="FRED vintage series: 4.5\n")
    monkeypatch.setitem(router.VENDOR_METHODS, "get_balance_sheet", {"sec_edgar": vendor})
    monkeypatch.setitem(router.VENDOR_METHODS, "get_macro_indicators", {"fred": fred})
    config = {"results_dir": str(tmp_path),
              "data_vendors": {"fundamental_data": "sec_edgar", "macro_data": "fred"},
              "evidence_tool_providers": {"get_balance_sheet": ["sec_edgar"], "get_macro_indicators": ["fred"]}}
    return config, EvidenceStore(tmp_path / "evidence"), vendor, fred


def test_capture_and_replay_exact_text_without_vendors(setup):
    config, store, vendor, fred = setup
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        balance = router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
        macro = router.route_to_vendor("get_macro_indicators", "CPI", "2026-01-06")
    ids = [ref["evidence_id"] for ref in run["tool_evidence"]]
    assert len(ids) == 2
    vendor.side_effect = fred.side_effect = AssertionError("must not access provider")
    with replay_tools(store, ids):
        assert router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06") == balance
        assert router.route_to_vendor("get_macro_indicators", "CPI", "2026-01-06") == macro
        with pytest.raises(EvidenceReplayError):
            router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-07")
        with pytest.raises(EvidenceReplayError):
            router.route_implementations("get_macro_indicators", {"fred": fred}, (), {})
    assert vendor.call_count == fred.call_count == 1
    assert store.get(ids[0])["payload"]["availability_basis"] == "unknown"


def test_optional_macro_capture_failure_is_not_swallowed(setup, monkeypatch):
    config, _, _, _ = setup
    monkeypatch.setattr(EvidenceStore, "put", Mock(side_effect=OSError("disk")))
    with run_config(config), pytest.raises(EvidenceCaptureError), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        router.route_to_vendor("get_macro_indicators", "CPI", "2026-01-06")
    assert run["status"] == "failed"


def test_failed_vendor_is_not_captured_and_actual_fallback_is(setup, monkeypatch):
    config, store, vendor, _ = setup
    monkeypatch.setitem(router.VENDOR_METHODS["get_balance_sheet"], "yfinance", Mock(side_effect=VendorUnavailableError("offline")))
    config["data_vendors"]["fundamental_data"] = "yfinance,sec_edgar"
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
    assert len(run["tool_evidence"]) == 1
    assert store.get(run["tool_evidence"][0]["evidence_id"])["payload"]["provider"] == "sec_edgar"
    vendor.assert_called_once()


def test_conflicting_calls_require_explicit_evidence_selection(setup):
    config, store, vendor, _ = setup
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
        vendor.return_value = "revised response"
        router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
    ids = [r["evidence_id"] for r in run["tool_evidence"]]
    with pytest.raises(EvidenceReplayError, match="conflicting"), replay_tools(store, ids):
        pass
    with replay_tools(store, [ids[1]]):
        assert router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06") == "revised response"


def test_disabled_capture_and_empty_replay(setup):
    config, store, vendor, _ = setup
    config["evidence_tool_providers"] = {}
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
    assert run["tool_evidence"] == []
    with replay_tools(store, []), pytest.raises(EvidenceReplayError):
        router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
    with run_config(config):
        router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
    assert vendor.call_count == 2


def test_nested_replay_restores_outer_selection(setup):
    config, store, _, _ = setup
    with run_config(config), analysis_run(config, "AAPL", "2026-01-06", []) as run:
        expected = router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
    ids = [r["evidence_id"] for r in run["tool_evidence"]]
    with replay_tools(store, ids):
        with replay_tools(store, []), pytest.raises(EvidenceReplayError):
            router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06")
        assert router.route_to_vendor("get_balance_sheet", "AAPL", "2026-01-06") == expected


def test_outcome_response_cannot_be_loaded_for_analysis(setup):
    _, store, _, _ = setup
    evidence_id = store.put(run_id="run1", tool="routed_tool_response", purpose="outcome", payload={})
    with pytest.raises(ValueError, match="purpose"), replay_tools(store, [evidence_id]):
        pass


@pytest.mark.parametrize("policy", [{"get_news": ["yfinance"]}, {"get_macro_indicators": ["sec_edgar"]}, "fred"])
def test_capture_policy_rejects_unsupported_tools_and_providers(setup, policy):
    config, _, vendor, fred = setup
    config["evidence_tool_providers"] = policy
    with pytest.raises(ValueError), analysis_run(config, "AAPL", "2026-01-06", []):
        pass
    vendor.assert_not_called()
    fred.assert_not_called()
