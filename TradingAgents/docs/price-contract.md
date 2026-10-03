# Shared daily price contract (F2, first delivery)

The stock-data tool, verified snapshot and memory settlement now use the same
provider adapters and adjustment convention. `data_vendors.core_stock_apis`
selects the chain; `tool_vendors.get_stock_data` overrides it for all three.
Only explicitly configured providers may be tried. Malformed or stale responses
are checked inside each attempt, so an explicitly configured fallback can serve
the request. Existing text sentinels remain available to agents; typed consumers
receive exceptions rather than prose masquerading as prices.

`dataflows.prices.get_price_history(symbol, start_date, end_date)` returns an
immutable `PriceHistory` containing immutable daily `PriceBar` records. Metadata
includes the requested and provider symbols, actual provider, inclusive date
range, UTC retrieval time, schema version, price and volume adjustment bases,
and currency (`None` when unknown). `to_frame()` returns an independent copy;
`to_text()` is the compatibility bridge for the stock-data tool. Numerical values
are not rounded before calculations.

## Price semantics

Yahoo is requested with explicit `auto_adjust=True`. Alpha Vantage's daily
adjusted endpoint returns raw OHLC plus adjusted close; the adapter scales OHLC
by adjusted-close/raw-close. Volume is left provider-reported and labelled as
such. This avoids interpreting a split as a price loss. Different feeds can still
have different corrections and corporate-action conventions; matching the label
does not prove their values identical.

Sources checked 2026-10-03:

- [yfinance history implementation](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py)
- [Alpha Vantage daily adjusted documentation](https://www.alphavantage.co/documentation/#dailyadj)

The Alpha Vantage endpoint is premium; this change does not subscribe to it or
make paid requests during tests. Existing Yahoo configurations continue to work.
Yahoo symbol aliases are applied only by the Yahoo adapter. Cross-provider symbol
mapping remains necessary for instruments whose identifiers differ.

Daily dates retain the provider's local session label, including mixed DST
UTC offsets. Rows outside the requested range are excluded, never forward-filled
or backfilled. Missing optional OHLCV cells remain missing; missing close rows
are excluded. Duplicate dates, invalid dates, non-finite values, negative volume
and contradictory OHLC relationships fail the provider attempt. Negative prices
are not universally rejected: futures can have valid negative prices. Settlement
retains its positive-close requirement.

The snapshot and stock-data text path retain a ten-calendar-day freshness guard.
Settlement uses an exclusive end date and requires a complete holding window;
it may retrieve dates after a past decision to score its outcome. That path is
not exposed as an analyst tool. Analyst tools retain their injected analysis-date
cutoff.

## Remaining F2 work

This delivery does not close all of F2:

- Exchange calendars, early closes and session-aware freshness replace the
  provisional ten-day rule in a later change.
- The standalone technical-indicator tool still uses its existing independently
  configured provider; only the snapshot's indicators use the new price contract.
- Currency, market, feed identifiers, publication/availability times, URLs and
  original-payload hashes need provider-specific enrichment. Retrieval time is
  not historical availability. Adjusted histories can be revised after the
  analysis date; this is not point-in-time evidence or a leakage-free backtest.
- Fundamentals and macro data still need their own typed contracts.
- Feed/benchmark provenance is returned by the price layer but not yet persisted
  with each settled outcome. Immutable evidence storage and replay belong to F3.
- Direct legacy Yahoo helper calls remain available for compatibility; application
  stock tools, snapshot and settlement use the new layer.

No new dependencies, LLM calls, GitHub Actions runs or live market requests are
needed for local validation:

```sh
cd TradingAgents
uv run --no-sync pytest -q
uv run --no-sync ruff check .
```

Validation recorded 2026-10-03: 1,163 tests and 91 subtests passed; one live
integration test deselected by the default offline policy. Ruff passed. These
results cover the local interpreter, not the blocked GitHub Actions matrix.
