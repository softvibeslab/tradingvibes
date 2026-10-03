"""Typed daily prices shared by verification and outcome scoring.

Dates are exchange-local sessions; ranges are inclusive. Adjusted history is
retrieved now, not a claim of point-in-time corporate-action availability.
"""
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from math import isfinite

import pandas as pd

from tradingagents.dataflows.calendars import session_close_at, validate_sessions
from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.contracts import AvailabilityBasis
from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError
from tradingagents.dataflows.router import route_implementations
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.alpha_vantage.stock import get_stock
from tradingagents.dataflows.vendors.yahoo.market import fetch_price_frame


@dataclass(frozen=True)
class PriceBar:
    session: date
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: float | None = None


@dataclass(frozen=True)
class PriceHistory:
    symbol: str
    provider_symbol: str
    provider: str
    start: date
    end: date
    retrieved_at: datetime
    bars: tuple[PriceBar, ...]
    adjustment: str = "split_dividend_adjusted"
    volume_basis: str = "provider_reported"
    currency: str | None = None
    schema_version: int = 1
    calendar_name: str | None = None
    cutoff_at: datetime | None = None
    # Lower bound only when a calendar supplies a scheduled close. Never equal
    # to retrieved_at. Vendor publication remains unknown.
    availability_basis: AvailabilityBasis = "unknown"
    available_not_before: datetime | None = None
    feed: str | None = None

    def to_frame(self) -> pd.DataFrame:
        """A fresh mutable view; callers cannot change the stored evidence."""
        return pd.DataFrame([
            {"Date": pd.Timestamp(b.session), "Open": b.open, "High": b.high,
             "Low": b.low, "Close": b.close, "Volume": b.volume}
            for b in self.bars
        ])

    def to_text(self) -> str:
        availability = self.availability_basis
        if self.available_not_before is not None:
            availability = f"{availability}; not_before={self.available_not_before.isoformat()}"
        return (
            f"# Stock data for {self.provider_symbol} from {self.start} to {self.end}\n"
            f"# Provider: {self.provider}; prices: {self.adjustment}; "
            f"volume: {self.volume_basis}; currency: {self.currency or 'unknown'}; "
            f"calendar: {self.calendar_name or 'unknown'}; "
            f"availability: {availability}; "
            f"retrieved_at: {self.retrieved_at.isoformat()} (not historical availability)\n"
            + self.to_frame().to_csv(index=False)
        )


def _with_availability(history: PriceHistory) -> PriceHistory:
    """Attach scheduled-close lower bound when a calendar is known."""
    if history.calendar_name is None or not history.bars:
        return replace(history, availability_basis="unknown", available_not_before=None)
    close = session_close_at(history.calendar_name, history.bars[-1].session)
    if close.tzinfo is None:
        close = close.replace(tzinfo=UTC)
    return replace(
        history,
        availability_basis="scheduled_session_close",
        available_not_before=close.astimezone(UTC),
    )


def _normalize(frame, symbol, provider_symbol, provider, start, end):
    if frame is None or frame.empty:
        raise NoMarketDataError(symbol, provider_symbol, "no price rows")
    if "Date" not in frame or "Close" not in frame:
        raise VendorUnavailableError(f"{provider}: price response lacks Date or Close")
    bars = []
    seen = set()
    for row in frame.to_dict("records"):
        try:
            # Keep the vendor's local session, including across DST changes.
            stamp = pd.Timestamp(row["Date"])
            if pd.isna(stamp):
                raise ValueError("missing date")
            session = stamp.date()
            if not start <= session <= end:
                continue
            if session in seen:
                raise ValueError("duplicate session")
            seen.add(session)
            values = {}
            for field in ("Open", "High", "Low", "Close", "Volume"):
                value = row.get(field)
                if value is None or pd.isna(value):
                    values[field.lower()] = None
                else:
                    value = float(value)
                    if not isfinite(value):
                        raise ValueError("non-finite value")
                    values[field.lower()] = value
            if values["close"] is None:
                continue
            high, low = values["high"], values["low"]
            if high is not None and low is not None and high < low:
                raise ValueError("high below low")
            for field in ("open", "close"):
                value = values[field]
                if value is not None and (
                    (high is not None and value > high) or (low is not None and value < low)
                ):
                    raise ValueError(f"{field} outside high/low")
            if values["volume"] is not None and values["volume"] < 0:
                raise ValueError("negative volume")
            bars.append(PriceBar(session=session, **values))
        except (ValueError, TypeError, OverflowError) as exc:
            raise VendorUnavailableError(f"{provider}: invalid daily price data ({exc})") from exc
    if not bars:
        raise NoMarketDataError(symbol, provider_symbol, "no closes in requested range")
    return PriceHistory(symbol, provider_symbol, provider, start, end,
                        datetime.now(UTC), tuple(sorted(bars, key=lambda b: b.session)))


def _yahoo(symbol, start, end):
    canonical = normalize_symbol(symbol)
    frame = fetch_price_frame(symbol, str(start), str(end))
    return _normalize(frame, symbol, canonical, "yfinance", start, end)


def _alpha(symbol, start, end):
    # Yahoo aliases (e.g. GC=F) are not Alpha Vantage symbol identifiers.
    canonical = symbol.strip().upper()
    raw = get_stock(canonical, str(start), str(end))
    try:
        frame = pd.read_csv(StringIO(raw), comment="#").rename(columns={
            "timestamp": "Date", "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        })
        # DAILY_ADJUSTED supplies raw OHLC and a separate adjusted close.
        # Apply its ratio to OHLC only; volume retains the provider's basis.
        ratio = pd.to_numeric(frame["adjusted_close"]) / pd.to_numeric(frame["Close"])
        if not ratio.map(lambda x: isfinite(x) and x > 0).all():
            raise ValueError("invalid adjustment factor")
        for field in ("Open", "High", "Low", "Close"):
            frame[field] = pd.to_numeric(frame[field]) * ratio
    except (ValueError, TypeError, KeyError) as exc:
        raise VendorUnavailableError("alpha_vantage: invalid adjusted price response") from exc
    return _normalize(frame, symbol, canonical, "alpha_vantage", start, end)


def fetch_provider_history(provider, symbol, start_date, end_date, *, max_stale_days=None):
    """Validate within each attempt so malformed/stale data can trigger fallback."""
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    history = {"alpha_vantage": _alpha, "yfinance": _yahoo}[provider](symbol, start, end)
    history = replace(history, feed=provider)
    config = get_config()
    calendar = config.get("price_calendars", {}).get(symbol.strip().upper())
    if calendar is not None:
        history = validate_sessions(
            history, calendar,
            max_missing_sessions=(config.get("price_max_missing_sessions", 1)
                                  if max_stale_days is not None else None),
        )
        return _with_availability(history)
    if max_stale_days is not None and (end - history.bars[-1].session).days > max_stale_days:
        raise NoMarketDataError(symbol, history.provider_symbol, "latest price is stale")
    return _with_availability(history)


def get_price_history(symbol: str, start_date: str, end_date: str, *, max_stale_days=None, _capture=True) -> PriceHistory:
    """Use exactly the get_stock_data vendor chain, including tool overrides.

    Does not apply ``analysis_cutoff``: settlement may request dates after the
    decision. Analyst tools clamp through ``analyst_price_end`` / snapshot.
    """
    from functools import partial

    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must not be after end_date")
    implementations = {
        provider: partial(fetch_provider_history, provider, max_stale_days=max_stale_days)
        for provider in ("alpha_vantage", "yfinance")
    }
    history = route_implementations(
        "get_stock_data", implementations, (symbol, start_date, end_date), {}, strict=True,
    )
    from tradingagents.evidence.capture import capture_prices

    return capture_prices(history) if _capture else history


def analyst_price_end(symbol: str, end: date) -> date:
    """Clamp an analyst end date when ``analysis_cutoff`` is configured.

    Settlement and outcome scoring must not call this — they need later sessions.
    """
    from tradingagents.dataflows.calendars import latest_closed_session

    config = get_config()
    cutoff = config.get("analysis_cutoff")
    if cutoff is None:
        return end
    if isinstance(cutoff, str):
        cutoff = datetime.fromisoformat(cutoff)
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("analysis_cutoff must include a timezone")
    calendar = config.get("price_calendars", {}).get(symbol.strip().upper())
    if calendar is None:
        raise ValueError(
            "analysis_cutoff requires an explicit price_calendars entry for "
            f"{symbol.strip().upper()}"
        )
    return min(end, latest_closed_session(calendar, cutoff))


def get_closes(symbol: str, start_date: str, end_date: str) -> pd.Series:
    """Outcome-only daily closes; preserve the existing EXCLUSIVE end contract."""
    end = date.fromisoformat(end_date) - timedelta(days=1)
    from tradingagents.evidence.capture import outcome_prices

    with outcome_prices():
        history = get_price_history(symbol, start_date, str(end))
    return pd.Series([b.close for b in history.bars],
                     index=pd.DatetimeIndex([b.session for b in history.bars]), dtype=float)


def get_closed_price_history(symbol: str, start_date: str, cutoff: datetime) -> PriceHistory:
    """Prices through the last scheduled close at an explicit aware instant.

    Requires an explicitly assigned calendar. It excludes an open session,
    but cannot establish when a provider actually published or revised a bar.
    """
    from tradingagents.dataflows.calendars import latest_closed_session

    calendar = get_config().get("price_calendars", {}).get(symbol.strip().upper())
    if calendar is None:
        raise ValueError("instant-based prices require an explicit price_calendars entry")
    end = latest_closed_session(calendar, cutoff)
    if date.fromisoformat(start_date) > end:
        raise NoMarketDataError(symbol, detail="no closed session in requested window")
    from tradingagents.evidence.capture import capture_prices

    history = get_price_history(symbol, start_date, str(end), max_stale_days=10, _capture=False)
    return capture_prices(replace(history, cutoff_at=cutoff.astimezone(UTC)))
