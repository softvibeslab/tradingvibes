# Protocolo de actualización

Base: 2026-10-03, commit 8b22d43d01d9ddda5d686d093d5385884622f3de. Actualizar antes de implementar o contratar; después mensualmente mientras dure el piloto.

| Objetivo | Qué verificar | Disparador |
|---|---|---|
| Checkout TradingAgents | Cambio de router, snapshot Yahoo, settlement, backtest y manifiesto | Actualización upstream |
| MCP adapters y LangGraph | Dependencias, async/sesiones, schema, compatibilidad | Cambio de lock |
| Anthropic skills | Rutas, licencia, prompts y conectores; guardar commit | Antes de copiar/adaptar |
| LangChain Docs/Reference, Context7 | Endpoints, autenticación y límites | Fallos o cambio de versión |
| Alpaca | Precio, feed IEX/SIP, derechos, MCP/CLI alpha y schema | Antes de piloto/contrato |
| Massive/Financial Datasets | Entitlements, precios, cobertura, restatements y publicación | Antes de elegir proveedor |
| SEC/FRED/Banxico | Políticas de consulta, publicación y vintages | Cambio de contrato o dato revisado |
| LangSmith/Phoenix/Langfuse | Retención, exportación, SDK, costos | Elección de observabilidad |
| vectorbt/LEAN/Nautilus | Licencias, datos, cuenta y modelo de fill | Decidir ejecución |
| Hipótesis H1–H4 | Evidencia experimental, ablations, métricas prospectivas | Cada experimento |

Guardar cambios en diffs/AAAA-MM-DD_delta.md: fuente anterior/nueva, fecha, hecho cambiado, efecto en recomendación y prueba pendiente. No reemplazar retrospectivamente el expediente original. Actualizar costos con plan/moneda/uso explícitos. Reabrir decisión si una mejora no supera baseline, si cambia la licencia o si un vendor no reconstruye información disponible en fecha.
