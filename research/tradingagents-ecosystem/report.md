# Informe — Ecosistema de valor para TradingAgents

## 1. Qué es este repo (mapa local)

**TradingAgents** es un framework multi-agente LLM (LangGraph) que simula un desk de trading:

| Capa | Contenido |
|------|-----------|
| Analistas | market, news, fundamentals, sentiment |
| Debate | bull / bear → research manager |
| Decisión | trader → risk (aggressive/conservative/neutral) → portfolio manager |
| Datos | router con vendors: yfinance, Alpha Vantage, FRED, Polymarket, SEC EDGAR, StockTwits, Reddit |
| Ops | CLI Typer (`tradingagents`), Docker, backtest grid, portfolio JSON, memory log, checkpoint SQLite |
| LLM | OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter, Ollama, Azure, Bedrock opcional |

**No es un broker.** Produce señales/decisiones de investigación; no envía órdenes.

Gaps estructurales más claros:
1. Datos OHLCV dependen mucho de scrapes (yfinance) o cuotas bajas (AV free).
2. Sin capa de ejecución paper ni HITL formal antes de “actuar”.
3. Alt-data limitado a social (Reddit/StockTwits) + Polymarket.
4. Memoria = log markdown + reflexión; no memoria jerárquica tipo FinMem.
5. Sin superficie MCP propia (Cursor/Claude no “hablan” al grafo nativamente).

---

## 2. Hallazgos priorizados

### P0 — máximo ROI

| Recurso | Tipo | Por qué aporta |
|---------|------|----------------|
| [Alpaca MCP](https://github.com/alpacahq/alpaca-mcp-server) + [Alpaca CLI](https://github.com/alpacahq/cli) | MCP + CLI | Paper trading, posiciones reales, bridge decisión → orden con guardrails |
| [OpenBB MCP](https://pypi.org/project/openbb-mcp-server) + [OpenBB CLI](https://docs.openbb.co/odp/cli) | MCP + CLI | Bus multi-provider (polygon, tiingo, fmp, yfinance…) sin N clientes |
| [Alpha Vantage MCP](https://mcp.alphavantage.co/) | MCP | Ya tenéis vendor AV; el MCP oficial acelera prototipos en Cursor |
| [Massive/Polygon](https://massive.com/stocks) | API | OHLCV/corp actions más estables que yfinance para backtests |
| [Finnhub](https://finnhub.io/) | API | News + quotes free generoso → news/sentiment agents |
| [SEC EDGAR MCP](https://github.com/stefanoamorelli/sec-edgar-mcp) | MCP | XBRL/insiders más precisos que el scrape actual |
| [LangGraph interrupts/HITL](https://docs.langchain.com/oss/python/langgraph/interrupts) | Docs | Gate humano antes de cualquier broker |
| [LLMQuant/skills](https://github.com/LLMQuant/skills) | Skills | Workflows equities/options/macro/risk para desarrollar el repo en Cursor |
| [AI Hedge Fund](https://github.com/virattt/ai-hedge-fund) | Framework | Personas de inversor + módulos valuation/sentiment reutilizables |
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | Framework | Valoración determinística (DCF/comps) + IC memos con provenance |

### P1 — alto valor, segundo sprint

| Recurso | Tipo | Gap |
|---------|------|-----|
| [Twelve Data](https://twelvedata.com/artificial-intelligence) | API + MCP nativo | Multi-mercado + indicadores server-side |
| [Tiingo](https://www.tiingo.com) | API | EOD limpio para backtest |
| [Quiver MCP](https://api.quiverquant.com/mcp-server/) | MCP (pago) | Congreso, dark pool, 13F — alt-data serio |
| [aitrados finance-trading-ai-agents-mcp](https://github.com/aitrados/finance-trading-ai-agents-mcp) | MCP OSS | Arquitectura “departamentos” + broker tools |
| [yfinance-mcp](https://github.com/narumiruna/yfinance-mcp) | MCP | Charts/options/screeners sin key (dev) |
| [claude-trading-skills](https://github.com/metavox/claude-trading-skills) / [everything-claude-trading](https://github.com/brainbytes-dev/everything-claude-trading) | Skills | Backtest, riesgo, pairs, DeFi playbooks |
| [FinMem](https://github.com/xt2201/finmem) | Paper+code | Memoria por capas para multi-día |
| [LEAN CLI](https://github.com/QuantConnect/lean-cli) | CLI | Backtest institucional vs grid LLM |
| [FinWorld survey](https://arxiv.org/html/2508.02292v1) | Paper | Benchmarking multi-agente trading |
| NewsAPI / Benzinga | APIs | News wire más allá de Yahoo |

### P2 — niche / más adelante

- Unusual Whales (options flow, caro)
- VectorBT PRO CLI/MCP (backtests vectorizados, pago)
- IBKR vía LEAN (live producción)
- QuantHarness / PrimoAgent (patrones técnicos más simples)
- Crypto MCP (CCXT) si ampliáis BTC-USD más allá de yfinance

---

## 3. Skills concretas para Cursor (este monorepo)

Instalables como Agent Skills (no sustituyen el runtime LangGraph):

```bash
# Catálogo finance con evidencia de datos
npx skills add LLMQuant/skills -a cursor

# Colección trading/quant (62–82 skills según repo)
# clonar o instalar desde metavox/claude-trading-skills o brainbytes-dev/everything-claude-trading
```

Skills más alineadas con gaps del repo:
- regime-detection, feature engineering, risk (VaR/drawdown)
- options-pricing / unusual activity (si añadís options)
- event-driven / alternative-data (para ampliar sentiment)
- backtest / trade journaling (mejorar `run_backtest`)

---

## 4. Orden de adopción recomendado

1. **Datos:** interfaz vendor nueva → Massive o Finnhub (o OpenBB como fachada).
2. **Fundamentals:** SEC EDGAR MCP / XBRL tools → fundamental analyst.
3. **HITL:** interrupt LangGraph antes de cualquier side-effect.
4. **Paper exec:** Alpaca MCP + CLI; PM lee posiciones reales.
5. **Patrones:** personas (AI Hedge Fund) + valoración (FinRobot) + memoria (FinMem).
6. **Alt-data:** Quiver cuando haya presupuesto.
7. **Eval:** LEAN o VectorBT para validar señales LLM fuera del grid actual.

---

## 5. Adversarial / riesgos

- **No mezclar MCP de broker con el grafo research sin HITL** — riesgo de órdenes accidentales.
- yfinance-MCP duplica lo que ya tenéis; valor bajo en runtime, alto solo para chat exploratorio.
- Free tiers AV (25/día) y NewsAPI (dev-only) rompen backtests largos.
- Skills de “trading” a menudo asumen ejecución DeFi/crypto; filtrar ruido.
- FinRobot/AI Hedge Fund son stacks grandes: **estudiar patrones**, no merge completo.

---

## 6. Conclusión

TradingAgents ya es un scaffold sólido (debate + structured output + memory + backtest). El valor externo más alto no es “otro framework de agentes”, sino: **datos fiables (OpenBB/Massive/Finnhub)**, **SEC más rico**, **paper execution (Alpaca)**, **HITL LangGraph**, y **skills/docs** para acelerar desarrollo en Cursor. Los papers/frameworks hermanos (FinRobot, FinMem, AI Hedge Fund, FinWorld) sirven como biblioteca de patrones, no como reemplazo.
