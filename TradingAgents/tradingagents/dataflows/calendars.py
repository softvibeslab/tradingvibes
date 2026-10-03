"""Explicit exchange calendars; a scheduled close is not publication evidence."""
from datetime import date, datetime, timedelta
from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd


@lru_cache(maxsize=32)
def _calendar(name: str, first_year: int, last_year: int):
    return xcals.get_calendar(name, start=f"{first_year}-01-01", end=f"{last_year}-12-31")


def session_schedule(name: str, start: date, end: date) -> pd.DataFrame:
    """A copied schedule of session labels and UTC times within inclusive dates."""
    if start > end:
        raise ValueError("calendar start must not be after end")
    calendar = _calendar(name, start.year - 1, end.year + 1)
    return calendar.schedule.loc[str(start):str(end)].copy()


def latest_closed_session(name: str, cutoff: datetime) -> date:
    """Last scheduled close at/before an aware instant, including early closes.

    Separate from date-only analysis, whose cutoff means the end of a session
    date. This function never claims the provider has published the final bar.
    """
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must include a timezone")
    instant = pd.Timestamp(cutoff).tz_convert("UTC")
    # Padding also covers overnight sessions labelled with the following date.
    schedule = session_schedule(name, instant.date() - timedelta(days=370),
                                instant.date() + timedelta(days=2))
    closed = schedule[schedule["close"] <= instant]
    if closed.empty:
        raise ValueError("no completed session in calendar window")
    return closed.index[-1].date()


def session_close_at(name: str, session: date) -> datetime:
    """Scheduled UTC close for a session label. Not vendor publication time."""
    schedule = session_schedule(name, session, session)
    if schedule.empty:
        raise ValueError(f"{session} is not a {name} session")
    close = schedule.iloc[0]["close"]
    return pd.Timestamp(close).to_pydatetime()


def validate_sessions(history, name: str, *, max_missing_sessions: int | None = None):
    """Validate daily rows and optionally enforce session-based freshness."""
    from dataclasses import replace

    from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError

    if max_missing_sessions is not None and (
        type(max_missing_sessions) is not int or max_missing_sessions < 0
    ):
        raise ValueError("price_max_missing_sessions must be a non-negative integer")
    schedule = session_schedule(name, history.start, history.end)
    sessions = {stamp.date() for stamp in schedule.index}
    unexpected = [bar.session for bar in history.bars if bar.session not in sessions]
    if unexpected:
        raise VendorUnavailableError(
            f"{history.provider}: price row {unexpected[0]} is not a {name} session"
        )
    if max_missing_sessions is not None:
        missed = sum(session > history.bars[-1].session for session in sessions)
        if missed > max_missing_sessions:
            raise NoMarketDataError(
                history.symbol, history.provider_symbol,
                f"latest price is stale: missing {missed} {name} sessions "
                f"(allowed {max_missing_sessions})",
            )
    return replace(history, calendar_name=name)
