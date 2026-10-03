"""Provider-neutral verification using the configured stock-price feed."""
from datetime import date, timedelta

from tradingagents.dataflows.prices import get_price_history
from tradingagents.dataflows.snapshot_render import render_snapshot


def build_verified_market_snapshot(symbol, as_of_date, look_back_days=30, indicators=None):
    end = date.fromisoformat(as_of_date)
    history = get_price_history(
        symbol, str(end - timedelta(days=5 * 366)), str(end), max_stale_days=10,
    )
    rendered = render_snapshot(history.to_frame(), symbol, as_of_date, look_back_days, indicators)
    return (
        f"Provider: {history.provider}; prices: {history.adjustment}; "
        f"volume: {history.volume_basis}; currency: {history.currency or 'unknown'}\n\n"
        + rendered
    )
