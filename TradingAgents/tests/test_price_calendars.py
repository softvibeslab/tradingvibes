"""Real offline exchange schedules at the common price boundary."""
from datetime import date, datetime

import pandas as pd
import pytest

from tradingagents.dataflows import prices
from tradingagents.dataflows.calendars import latest_closed_session, session_schedule
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.runs.manifest import safe_settings


def configured(**extra):
    return run_config({"data_vendors": {"core_stock_apis": "yfinance"},
                       "price_calendars": {"AAPL": "XNYS"},
                       "price_max_missing_sessions": 0, **extra})


def serve(monkeypatch, dates):
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *args: pd.DataFrame({
        "Date": dates, "Close": [100.] * len(dates),
    }))


def test_holiday_and_weekend_do_not_count_as_missing(monkeypatch):
    serve(monkeypatch, ["2026-11-25"])
    with configured():
        result = prices.get_price_history("AAPL", "2026-11-25", "2026-11-26", max_stale_days=10)
    assert result.calendar_name == "XNYS"
    serve(monkeypatch, ["2026-11-27"])
    with configured():
        prices.get_price_history("AAPL", "2026-11-27", "2026-11-29", max_stale_days=10)


def test_a_missing_session_fails_even_within_ten_calendar_days(monkeypatch):
    serve(monkeypatch, ["2026-11-25"])
    with configured(), pytest.raises(NoMarketDataError, match="missing 1 XNYS sessions"):
        prices.get_price_history("AAPL", "2026-11-25", "2026-11-27", max_stale_days=10)


def test_non_session_rows_fail_instead_of_becoming_outcomes(monkeypatch):
    serve(monkeypatch, ["2026-11-26"])
    with configured(), pytest.raises(VendorUnavailableError, match="not a XNYS session"):
        prices.get_closes("AAPL", "2026-11-25", "2026-11-27")


def test_unconfigured_instruments_keep_existing_policy(monkeypatch):
    serve(monkeypatch, ["2026-11-26"])
    with configured():
        result = prices.get_price_history("BTC-USD", "2026-11-25", "2026-11-29", max_stale_days=10)
    assert result.calendar_name is None


@pytest.mark.parametrize(("cutoff", "session"), [
    ("2026-11-27T17:59:59+00:00", "2026-11-25"),
    ("2026-11-27T18:00:00+00:00", "2026-11-27"),
    ("2026-03-06T20:59:59+00:00", "2026-03-05"),
    ("2026-03-06T21:00:00+00:00", "2026-03-06"),
    ("2026-03-09T19:59:59+00:00", "2026-03-06"),
    ("2026-03-09T20:00:00+00:00", "2026-03-09"),
])
def test_completed_session_uses_early_close_and_dst(cutoff, session):
    assert latest_closed_session("XNYS", datetime.fromisoformat(cutoff)) == date.fromisoformat(session)


def test_naive_cutoff_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        latest_closed_session("XNYS", datetime(2026, 11, 27, 18))


def test_schedule_copy_does_not_mutate_cached_calendar():
    start, end = date(2026, 11, 25), date(2026, 11, 27)
    schedule = session_schedule("XNYS", start, end)
    schedule.loc[:, "close"] = pd.NaT
    assert session_schedule("XNYS", start, end)["close"].notna().all()


def test_settings_record_calendar_policy():
    settings = safe_settings({"price_calendars": {"AAPL": "XNYS"}, "price_max_missing_sessions": 0})
    assert settings["price_calendars"] == {"AAPL": "XNYS"}
    assert settings["price_max_missing_sessions"] == 0


@pytest.mark.parametrize("tolerance", [-1, True, 1.5, "1"])
def test_invalid_tolerance_is_rejected(monkeypatch, tolerance):
    serve(monkeypatch, ["2026-11-25"])
    with configured(price_max_missing_sessions=tolerance), pytest.raises(ValueError):
        prices.get_price_history("AAPL", "2026-11-25", "2026-11-27", max_stale_days=10)


def test_instant_query_excludes_open_session(monkeypatch):
    serve(monkeypatch, ["2026-11-25", "2026-11-27"])
    cutoff = datetime.fromisoformat("2026-11-27T17:59:59+00:00")
    with configured():
        history = prices.get_closed_price_history("AAPL", "2026-11-25", cutoff)
    assert history.end == date(2026, 11, 25)
    assert [bar.session for bar in history.bars] == [date(2026, 11, 25)]
    assert history.cutoff_at == cutoff


def test_instant_query_requires_calendar_and_closed_window(monkeypatch):
    serve(monkeypatch, ["2026-11-27"])
    cutoff = datetime.fromisoformat("2026-11-27T17:59:59+00:00")
    with configured():
        with pytest.raises(ValueError, match="explicit"):
            prices.get_closed_price_history("UNKNOWN", "2026-11-25", cutoff)
        with pytest.raises(NoMarketDataError, match="no closed session"):
            prices.get_closed_price_history("AAPL", "2026-11-27", cutoff)


def test_session_staleness_can_trigger_configured_fallback(monkeypatch):
    monkeypatch.setattr(prices, "get_stock", lambda *args:
                        "timestamp,open,high,low,close,adjusted_close,volume\n"
                        "2026-11-25,100,100,100,100,100,10\n")
    serve(monkeypatch, ["2026-11-27"])
    with configured(data_vendors={"core_stock_apis": "alpha_vantage,yfinance"}):
        history = prices.get_price_history("AAPL", "2026-11-25", "2026-11-27", max_stale_days=10)
    assert history.provider == "yfinance"
    assert history.calendar_name == "XNYS"
