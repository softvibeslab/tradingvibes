"""F2: availability metadata, CLI cutoff, typed fundamentals/macro provenance."""
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from cli import prompts, selections
from tradingagents.dataflows import prices
from tradingagents.dataflows.calendars import session_close_at
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.contracts import Provenance
from tradingagents.dataflows.fundamentals import FundamentalStatement, StatementColumn, StatementRow
from tradingagents.dataflows.vendors import sec_edgar
from tradingagents.runs.manifest import safe_settings


def configured(**extra):
    return run_config({
        "data_vendors": {"core_stock_apis": "yfinance"},
        "price_calendars": {"AAPL": "XNYS"},
        "price_max_missing_sessions": 0,
        **extra,
    })


def serve(monkeypatch, dates):
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *args: pd.DataFrame({
        "Date": dates, "Close": [100.] * len(dates),
        "Open": [100.] * len(dates), "High": [100.] * len(dates),
        "Low": [100.] * len(dates), "Volume": [1.] * len(dates),
    }))


def test_retrieval_time_is_never_treated_as_availability():
    now = datetime.now(UTC)
    with pytest.raises(ValueError, match="retrieved_at"):
        Provenance(
            provider="yfinance",
            availability_basis="unknown",
            retrieved_at=now,
            available_not_before=now,
        ).assert_not_retrieval_as_availability()


def test_calendar_prices_expose_scheduled_close_not_retrieval(monkeypatch):
    serve(monkeypatch, ["2026-11-25"])
    with configured():
        history = prices.get_price_history("AAPL", "2026-11-25", "2026-11-25", max_stale_days=10)
    assert history.availability_basis == "scheduled_session_close"
    assert history.available_not_before == session_close_at("XNYS", date(2026, 11, 25)).astimezone(UTC)
    assert history.available_not_before != history.retrieved_at
    assert "not historical availability" in history.to_text()


def test_unmapped_symbol_availability_is_unknown(monkeypatch):
    serve(monkeypatch, ["2026-11-26"])
    with configured():
        history = prices.get_price_history("BTC-USD", "2026-11-25", "2026-11-29", max_stale_days=10)
    assert history.availability_basis == "unknown"
    assert history.available_not_before is None


def test_analyst_end_clamps_open_session_when_cutoff_configured(monkeypatch):
    serve(monkeypatch, ["2026-11-25", "2026-11-27"])
    cutoff = datetime.fromisoformat("2026-11-27T17:59:59+00:00")
    with configured(analysis_cutoff=cutoff):
        assert prices.analyst_price_end("AAPL", date(2026, 11, 27)) == date(2026, 11, 25)
        history = prices.get_price_history("AAPL", "2026-11-25", "2026-11-27", max_stale_days=10)
        # Settlement path is unclamped: still returns the requested end.
        assert history.end == date(2026, 11, 27)


def test_parse_cutoff_requires_timezone():
    assert prompts.parse_analysis_cutoff("2026-11-27T12:59:59-05:00").tzinfo is not None
    with pytest.raises(ValueError, match="timezone"):
        prompts.parse_analysis_cutoff("2026-11-27T12:59:59")


def test_parse_calendar_rejects_unknown():
    assert prompts.parse_price_calendar("xnys") == "XNYS"
    with pytest.raises(ValueError, match="unknown"):
        prompts.parse_price_calendar("NOT_A_REAL_CAL")


def test_cutoff_flag_derives_date(monkeypatch):
    for name, value in {
        "TRADINGAGENTS_OUTPUT_LANGUAGE": "English",
        "TRADINGAGENTS_MAX_DEBATE_ROUNDS": "1",
        "TRADINGAGENTS_MAX_RISK_ROUNDS": "1",
        "TRADINGAGENTS_LLM_PROVIDER": "openai",
        "TRADINGAGENTS_QUICK_THINK_LLM": "gpt-6-luna",
        "TRADINGAGENTS_DEEP_THINK_LLM": "gpt-6-sol",
    }.items():
        monkeypatch.setenv(name, value)

    def no_prompt(*a, **k):
        raise AssertionError("prompted although flags/env answered the step")

    for step in ("get_ticker", "get_analysis_date", "select_analysts"):
        monkeypatch.setattr(selections, step, no_prompt)
    monkeypatch.setattr(selections, "fetch_announcements", lambda: None)
    monkeypatch.setattr(selections, "display_announcements", lambda *a: None)
    monkeypatch.setattr(selections, "ensure_api_key", lambda *a, **k: None)

    chosen = selections._prompt_selections({}, {
        "ticker": "AAPL",
        "cutoff": "2026-11-27T17:59:59+00:00",
        "calendar": "XNYS",
        "analysts": "market",
    })
    assert chosen["analysis_date"] == "2026-11-25"
    assert chosen["price_calendar"] == "XNYS"
    assert chosen["analysis_cutoff"].startswith("2026-11-27T17:59:59")


def test_unattended_gaps_accept_cutoff_instead_of_date():
    gaps = selections.unattended_gaps({
        "ticker": "AAPL", "cutoff": "x", "calendar": "XNYS",
        "analysts": "market", "save": True, "show": False,
    })
    assert not any(g.startswith("--date") for g in gaps)


def test_manifest_records_cutoff_and_calendars():
    settings = safe_settings({
        "analysis_cutoff": "2026-11-27T17:59:59+00:00",
        "price_calendars": {"AAPL": "XNYS"},
        "price_max_missing_sessions": 0,
    })
    assert settings["analysis_cutoff"] == "2026-11-27T17:59:59+00:00"
    assert settings["price_calendars"] == {"AAPL": "XNYS"}


def test_fundamental_statement_marks_filing_date_availability():
    statement = FundamentalStatement(
        ticker="AAPL",
        kind="balance_sheet",
        frequency="quarterly",
        as_of_date=date(2024, 6, 1),
        provider="sec_edgar",
        title="Balance Sheet",
        columns=(StatementColumn(period_end=date(2024, 3, 31), span_label=""),),
        rows=(StatementRow(label="Total Assets", unit="USD", cells=("100",)),),
        retrieved_at=datetime(2026, 10, 3, tzinfo=UTC),
        availability_basis="filing_date",
    )
    text = statement.to_text()
    assert "filed on or before 2024-06-01" in text
    assert "not historical availability" in text


def test_sec_build_statement_uses_typed_contract(monkeypatch):
    facts = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {"end": "2024-03-31", "val": 1e9, "filed": "2024-05-01", "form": "10-Q"},
                        ]
                    }
                }
            }
        }
    }
    monkeypatch.setattr(sec_edgar, "cik_for", lambda t: "0000320193")
    monkeypatch.setattr(sec_edgar, "_cached_json", lambda *a, **k: facts)
    statement = sec_edgar.build_statement(
        "balance_sheet", "AAPL", "quarterly", "2024-06-01", "Balance Sheet",
    )
    assert statement.availability_basis == "filing_date"
    assert statement.provider == "sec_edgar"
    assert "SEC EDGAR facts filed on or before 2024-06-01" in statement.to_text()
