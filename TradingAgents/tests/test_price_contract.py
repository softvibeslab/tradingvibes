"""Provider selection, adjustment and validation at the common price boundary."""
from dataclasses import FrozenInstanceError
from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from tradingagents.dataflows import prices, router, snapshot
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.memory import settlement


@pytest.fixture
def frame():
    return pd.DataFrame({
        "Date": ["2026-01-05", "2026-01-06"],
        "Open": [100., 101.], "High": [102., 103.], "Low": [99., 100.],
        "Close": [101., 102.], "Volume": [200., 300.],
    })


def config(vendor):
    return run_config({"data_vendors": {"core_stock_apis": vendor}})


def test_contract_immutable_and_views_independent(monkeypatch, frame):
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *a: frame)
    with config("yfinance"):
        result = prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
    assert result.provider == "yfinance"
    assert result.retrieved_at.tzinfo is not None
    assert result.adjustment == "split_dividend_adjusted"
    with pytest.raises(FrozenInstanceError):
        result.bars[0].close = 0
    result.to_frame().loc[0, "Close"] = 0
    assert result.bars[0].close == 101
    assert "Provider: yfinance" in result.to_text()


@pytest.mark.parametrize("mutation", ["duplicate", "infinite", "volume", "ohlc", "date", "schema"])
def test_invalid_data_is_provider_failure(monkeypatch, frame, mutation):
    if mutation == "duplicate":
        frame.loc[1, "Date"] = frame.loc[0, "Date"]
    elif mutation == "infinite":
        frame.loc[0, "Close"] = float("inf")
    elif mutation == "volume":
        frame.loc[0, "Volume"] = -1
    elif mutation == "ohlc":
        frame.loc[0, "High"] = 10
    elif mutation == "date":
        frame.loc[0, "Date"] = "not a date"
    else:
        frame = frame.drop(columns="Close")
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *a: frame)
    with config("yfinance"), pytest.raises(VendorUnavailableError):
        prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")


def test_local_dates_cutoff_and_no_fill(monkeypatch, frame):
    frame["Date"] = ["2026-03-06T00:00:00+09:00", "2026-03-09T00:00:00+09:00"]
    frame.loc[0, "Open"] = float("nan")
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *a: frame)
    with config("yfinance"):
        result = prices.get_price_history("7203.T", "2026-03-06", "2026-03-08")
    assert len(result.bars) == 1
    assert result.bars[0].session == date(2026, 3, 6)
    assert result.bars[0].open is None


def alpha_csv(frame):
    raw = frame.rename(columns={"Date": "timestamp", "Open": "open", "High": "high",
                                "Low": "low", "Close": "close", "Volume": "volume"}).copy()
    raw["adjusted_close"] = raw["close"] / 2
    return raw.to_csv(index=False)


def test_alpha_selected_for_text_snapshot_and_outcome(monkeypatch, frame):
    alpha = Mock(return_value=alpha_csv(frame))
    yahoo = Mock(side_effect=AssertionError("Yahoo must not be consulted"))
    monkeypatch.setattr(prices, "get_stock", alpha)
    monkeypatch.setattr(prices, "fetch_price_frame", yahoo)
    with config("alpha_vantage"):
        result = prices.get_price_history("aapl", "2026-01-05", "2026-01-06")
        text = router.route_to_vendor("get_stock_data", "aapl", "2026-01-05", "2026-01-06")
        snap = snapshot.build_verified_market_snapshot("aapl", "2026-01-06")
        raw, _, days, resolved = settlement.fetch_returns("aapl", "2026-01-05", 1)
    assert result.bars[0].close == 50.5
    assert result.bars[0].open == 50
    assert result.bars[0].volume == 200  # no dividend-ratio adjustment of volume
    assert "alpha_vantage" in text and "alpha_vantage" in snap
    assert "| Close | 51.00 |" in snap
    assert raw == pytest.approx(1 / 101)
    assert days == 1 and resolved == "2026-01-06"
    yahoo.assert_not_called()
    assert alpha.call_args_list[0].args[0] == "AAPL"


def test_tool_override_and_explicit_fallback(monkeypatch, frame):
    monkeypatch.setattr(prices, "get_stock", Mock(return_value="invalid CSV"))
    monkeypatch.setattr(prices, "fetch_price_frame", Mock(return_value=frame))
    with run_config({"data_vendors": {"core_stock_apis": "alpha_vantage"},
                     "tool_vendors": {"get_stock_data": "alpha_vantage,yfinance"}}):
        result = prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
    assert result.provider == "yfinance"
    prices.fetch_price_frame.reset_mock()
    with config("alpha_vantage"), pytest.raises(VendorUnavailableError):
        prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
    prices.fetch_price_frame.assert_not_called()


def test_stale_primary_can_fall_back(monkeypatch, frame):
    stale = frame.copy()
    stale["Date"] = ["2025-12-01", "2025-12-02"]
    monkeypatch.setattr(prices, "get_stock", lambda *a: alpha_csv(stale))
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *a: frame)
    with config("alpha_vantage,yfinance"):
        result = prices.get_price_history("AAPL", "2025-12-01", "2026-01-06", max_stale_days=10)
    assert result.provider == "yfinance"


def test_empty_and_exclusive_end(monkeypatch, frame):
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *a: frame)
    with config("yfinance"):
        closes = prices.get_closes("AAPL", "2026-01-05", "2026-01-06")
        assert closes.tolist() == [101]
        with pytest.raises(NoMarketDataError):
            prices.get_price_history("AAPL", "2025-01-01", "2025-01-02")
        with pytest.raises(ValueError):
            prices.get_price_history("AAPL", "2026-01-06", "2026-01-05")


def test_split_does_not_become_a_fifty_percent_loss(monkeypatch):
    raw = "timestamp,open,high,low,close,adjusted_close,volume\n2026-01-05,200,202,198,200,100,1000\n2026-01-06,100,101,99,100,100,2000\n"
    monkeypatch.setattr(prices, "get_stock", lambda *a: raw)
    with config("alpha_vantage"):
        closes = prices.get_closes("AAPL", "2026-01-05", "2026-01-07")
    assert closes.tolist() == [100, 100]


def test_dst_offsets_preserve_session_labels(monkeypatch):
    frame = pd.DataFrame({"Date": ["2026-03-06T00:00:00-05:00", "2026-03-09T00:00:00-04:00"],
                          "Close": [100, 101]})
    monkeypatch.setattr(prices, "fetch_price_frame", lambda *a: frame)
    with config("yfinance"):
        result = prices.get_price_history("AAPL", "2026-03-06", "2026-03-09")
    assert [b.session for b in result.bars] == [date(2026, 3, 6), date(2026, 3, 9)]


def test_unavailable_is_typed_for_scoring_and_text_for_agent(monkeypatch):
    monkeypatch.setattr(prices, "fetch_price_frame", Mock(side_effect=VendorUnavailableError("offline")))
    with config("yfinance"):
        with pytest.raises(VendorUnavailableError):
            prices.get_price_history("AAPL", "2026-01-05", "2026-01-06")
        assert router.route_to_vendor("get_stock_data", "AAPL", "2026-01-05", "2026-01-06").startswith("DATA_UNAVAILABLE")
        assert settlement.fetch_returns("AAPL", "2026-01-05") == (None, None, None, None)
