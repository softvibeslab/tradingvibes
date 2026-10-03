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

## F2 third delivery (availability, CLI cutoff, fundamentals/macro)

- Prices carry `availability_basis` and optional `available_not_before`. With an
  assigned calendar the basis is `scheduled_session_close` (scheduled UTC close
  of the latest bar). That is a lower bound only — not vendor publication.
  Without a calendar the basis is `unknown` and `available_not_before` is null.
  `retrieved_at` is labelled as operational and is never copied into availability.
- CLI: `--cutoff` (aware ISO instant) with `--calendar` (e.g. `XNYS`) derives the
  analysis session date, sets `analysis_cutoff` and `price_calendars[TICKER]`, and
  records both in the run manifest. Analyst stock text and the verified snapshot
  clamp through `analyst_price_end`; settlement/`get_closes` do not.
- Fundamentals: `dataflows.fundamentals.FundamentalStatement` with
  `availability_basis=filing_date` for SEC EDGAR (`build_statement` → `to_text`).
  Macro: FRED responses are wrapped with `fred_realtime_vintage` provenance.
- Still open for later phases: standalone indicator tool vendor unification;
  payload hashes/URLs; persisting feed provenance on settled outcomes; F3 evidence
  archive. Adjusted histories can still be revised after the analysis date.

The first delivery added no dependencies; the second adds the calendar package.
No LLM calls, GitHub Actions runs or live market requests are needed for validation:

```sh
cd TradingAgents
uv run --no-sync pytest -q
uv run --no-sync ruff check .
```

Validation recorded 2026-10-03: 1,163 tests and 91 subtests passed; one live
integration test deselected by the default offline policy. Ruff passed. These
results cover the local interpreter, not the blocked GitHub Actions matrix.

## Session calendars (second F2 delivery)

Install from the updated lock (`uv sync --locked --extra dev --extra bedrock`).
`exchange-calendars` is now a core dependency, locked to 4.13.2. Assign calendars
explicitly in the graph configuration, using the **requested uppercase symbol**:

```python
config["price_calendars"] = {"AAPL": "XNYS", "SPY": "XNYS"}
config["price_max_missing_sessions"] = 0
```

No exchange is inferred from a ticker. The assignment is configuration, not
provider-verified listing metadata. Unmapped symbols keep the ten-calendar-day
freshness rule. Mapped symbols reject bars on non-session dates and count missing
sessions after the latest bar instead of elapsed calendar days. A configured
fallback is still attempted on stale or invalid data. The default tolerance is
one missing session; zero requires the latest expected session. This checks tail
freshness, not completeness of every interior session in the historical window.

Dates in existing analyst tools still mean a session-date cutoff, including that
date's bar. This is intentionally distinct from the new Python API for an instant:

```python
from datetime import datetime
from tradingagents.dataflows.config import run_config
from tradingagents.dataflows.prices import get_closed_price_history

with run_config(config):
    history = get_closed_price_history(
        "AAPL", "2026-11-01", datetime.fromisoformat("2026-11-27T12:59:59-05:00")
    )
```

This example excludes November 27's still-open session. Its scheduled early close
is 13:00 New York time. The API requires an explicit calendar and an aware cutoff;
it records the UTC cutoff and calendar in the result. `calendars.latest_closed_session`
uses scheduled close times, including DST and early closes. The existing CLI and
analyst tools remain date-based; they do not silently switch to this instant API.

The schedule does **not** prove a vendor has published a final bar, nor prevent
later corporate-action revisions. Publication timestamps and point-in-time data
remain open work. Calendar definitions also require maintenance for exceptional
closures. See the upstream [calendar documentation](https://github.com/gerrymanoim/exchange_calendars/blob/master/README.md).

Calendar configuration and missing-session tolerance are included in run manifests.
Settlement validates configured session labels, but does not demand that the
entire future query window has already traded; its existing holding-window check
continues to decide when an outcome is ready.

Second-delivery validation (2026-10-03): 1,183 tests and 91 subtests passed; one
live integration test deselected. Ruff passed and pip-audit found no known
vulnerabilities in the locked application/dev/Bedrock dependency set. All checks
ran locally; no GitHub Actions job was triggered.

### CLI cutoff example

```bash
tradingagents --ticker AAPL \
  --cutoff 2026-11-27T12:59:59-05:00 --calendar XNYS \
  --analysts market,news --save --no-show
```

This sets the analysis date to the last XNYS session closed at that instant
(2026-11-25 for the Thanksgiving early-close week) and clamps analyst prices
accordingly.
