# Plan — Deep research ecosistema TradingAgents

## Pregunta
¿Qué skills, documentación, MCPs, APIs, CLIs y frameworks externos aportan valor real al repo local `TradingAgents/` (fork/copia de TauricResearch)?

## Hipótesis (a validar)
1. El gap principal es **ejecución paper + datos institucionales**, no más agentes de debate.
2. Los MCP oficiales (Alpaca, OpenBB, Alpha Vantage, Twelve Data/Massive) son el puente más barato hacia Cursor/Claude sin reescribir el grafo.
3. Skills de quant (LLMQuant, claude-trading-skills) mejoran el **desarrollo del repo**, no el runtime de LangGraph.
4. FinRobot / AI Hedge Fund / FinMem aportan patrones (valoración, personas, memoria) más que código drop-in.

## Método
- Mapeo del repo (README, pyproject, dataflows/router, agents).
- Triangulación: WebSearch + subagente web-researcher + docs GitHub/arXiv.
- Bright Data: 401 (no usable en esta sesión).

## Criterios de valor
- Cierra un gap concreto del router/vendors o del grafo.
- Licencia/mantenimiento razonable.
- Free tier o path paper-safe.
- Prioridad P0/P1/P2.
