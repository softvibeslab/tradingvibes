# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

TradingAgents is a multi-agent LLM trading framework built on LangGraph (upstream: TauricResearch/TradingAgents). It ships a Python package (`tradingagents/`) and an interactive Typer/Rich CLI (`cli/`).

## Commands

```bash
pip install -e ".[dev]"          # dev install (ruff, pytest); add [bedrock] for AWS Bedrock
pytest -q                        # full suite (integration tests excluded by default)
pytest tests/test_symbols.py -q  # one file
pytest tests/test_symbols.py::test_name -q   # one test
pytest -m integration            # only tests that hit real services (need real API keys)
ruff check .                     # lint — CI runs this strict over the whole repo
tradingagents                    # interactive CLI (or: python -m cli.main)
tradingagents --ticker NVDA --date 2026-09-23 --analysts market,news --save --no-show  # unattended
tradingagents backtest           # backtest subcommand
python main.py                   # minimal programmatic example
```

CI (`.github/workflows/ci.yml`) runs pytest on Python 3.11–3.14 plus one run with `TZ=America/New_York` (tests must not depend on UTC), a clean non-dev install that must `import tradingagents, cli.main` (catches undeclared runtime deps), and `ruff check .`. Ruff: line length 100, rules `E,W,F,I,B,UP,C4,SIM`; do not mass-run `ruff format` (deliberately deferred).

## Test harness (tests/conftest.py)

The conftest enforces invariants every test relies on — keep new tests compatible:
- **No network**: sockets and curl_cffi (yfinance) are patched to raise. A test that needs the network must be `@pytest.mark.integration`.
- All `TRADINGAGENTS_*` env vars are blanked before import, and results/cache/memory-log paths point to a temp dir, so a developer's `.env` never leaks into assertions.
- Provider API keys are set to `"placeholder"`; the global dataflows config is reset to `DEFAULT_CONFIG` around every test; CLI prefs go to `tmp_path`; `stdin.isatty()` is True unless a test overrides it.
- Markers are strict (`unit`, `integration`, `smoke`).

## Architecture

**Graph flow** (`tradingagents/graph/`): `TradingAgentsGraph` (`trading_graph.py`) is the entry point; `propagate(ticker, trade_date)` returns `(final_state, decision)`. `setup.py` builds the LangGraph:
1. Selected analysts (`market`, `social`/sentiment, `news`, `fundamentals`) run **in parallel**, each as its own subgraph with a private message history and a `max_tool_rounds` cap, returning only its report key.
2. Bull ↔ Bear researcher debate → Research Manager.
3. Trader.
4. Aggressive / Conservative / Neutral risk debate → Portfolio Manager (final decision).

Two LLM tiers: `quick_think_llm` for analysts/researchers/trader/debators, `deep_think_llm` for Research Manager and Portfolio Manager. Debate routing is in `conditional_logic.py`; every conditional edge maps all possible targets (`DEBATE_PATH_MAP`, `RISK_ANALYSIS_PATH_MAP`) so label drift can't crash a run. Shared state is `agents/state.py`.

**Agents** (`tradingagents/agents/`): factory functions `create_*` per role. Tools exposed to LLMs are in `agents/tools.py`; structured output schemas in `schemas.py`/`structured.py`.

**Data layer** (`tradingagents/dataflows/`): `router.py` maps each tool to a vendor chain from config (`data_vendors` per category, `tool_vendors` per tool). The configured chain is exact — no silent routing to unchosen vendors. Vendors live in `dataflows/vendors/` (yahoo, alpha_vantage, sec_edgar, fred, polymarket, reddit, stocktwits) and must raise the `VendorError` hierarchy from `errors.py` (`NoMarketDataError`, `VendorUnavailableError`, `VendorNotConfiguredError`); the router reacts by error type, not by vendor.

**LLM providers** (`tradingagents/llm_clients/`): `factory.py` builds a client per `llm_provider`; per-provider clients, model catalog, capability flags, and API-key env mapping live alongside.

**Memory & evaluation**: `memory/` keeps a markdown decision log, reflection, and settlement of pending decisions against `holding_period_days` and a per-exchange benchmark (`benchmark_map`). `backtest.py` and `reporting.py` handle backtests and saved report trees.

## Invariants enforced by tests

- **Point-in-time / no look-ahead**: dated tools take `trade_date` from graph state (injected, hidden from the model schema), and `dataflows/date_window.py` clamps every window to the trade date. Never let a tool or vendor fetch data later than the analysis date; many `test_*_lookahead.py` / `test_*_pointintime.py` tests guard this.
- **Layering**: only `tradingagents/dataflows/` may import vendor libraries such as `yfinance` (`test_layering.py`).
- **Output language**: every report-producing agent must call `get_language_instruction()`; add new ones to `REPORT_AGENTS` in `test_i18n_coverage.py`.

## Configuration

`tradingagents/default_config.py` is the single source of defaults (`DEFAULT_CONFIG`, built at import). To make a key overridable from the environment, add a row to `_ENV_OVERRIDES`; values are coerced to the default's type and invalid values raise. `.env` is loaded on import; see `.env.example` (and `.env.enterprise.example` for Azure). Runtime data defaults to `~/.tradingagents/` (logs, cache, memory).

User-facing changes are recorded in `CHANGELOG.md` (Keep a Changelog format, with issue numbers).
