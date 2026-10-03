# Datos, APIs, MCP y CLI: aportación a TradingAgents

Investigación consultada el 2026-10-03. Las recomendaciones son juicio de integración, no afirmaciones de rentabilidad. Sólo se leyeron código y fuentes públicas; no se instalaron servicios ni probaron endpoints con credenciales.

## Lo que ya existe

`tradingagents/dataflows/router.py` contiene categorías de OHLCV, indicadores, fundamentales, noticias, macro y prediction markets. Vendors existentes: Yahoo, Alpha Vantage, SEC EDGAR, FRED y Polymarket. `default_config.py` respeta cadenas explícitas de vendors y permite overrides por herramienta. SEC ya filtra facts por `filed <= as_of_date`; FRED fija `realtime_start` y `realtime_end`, con pruebas de vintage y timezone. También existen pruebas de lookahead de noticias/fundamentales, unidades, identidad del instrumento, límites temporales y fallbacks.

Por ello, agregar “SEC/FRED para evitar lookahead” sería duplicación. El siguiente paso valioso es aumentar procedencia y granularidad temporal, y ofrecer una fuente de precios alternativa bajo el contrato actual. El filtro diario de filed no basta, por sí solo, para una futura simulación intradía: un filing publicado después del cierre no debe estar disponible esa mañana (inferencia técnica).

## Priorización

| Recurso | Valor incremental | Encaje | Decisión |
|---|---|---|---|
| [SEC](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) + [ALFRED](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html) | Más trazabilidad y control de revisiones | Enriquecer vendors existentes con accession/publication/retrieval/vintage | P0, conservar y ampliar |
| [Massive](https://www.massive.com/docs/ai-tools/quickstart) | Proveedor alternativo, SDK Python, MCP y llms.txt | Nuevo vendor opt-in para precios/noticias; MCP para investigación | P1, piloto comparativo |
| [Financial Datasets](https://docs.financialdatasets.ai/api/financials/income-statements) | Estados normalizados y originales con filing_datetime y accession | Benchmark contra SEC, luego adapter específico | P1, verificar restatements/PIT antes de adoptar |
| [Alpaca Market Data](https://docs.alpaca.markets/us/docs/about-market-data-api) | Segundo feed y ruta futura a paper trading | Datos primero; ejecución en capa independiente | P1 datos, P2 paper |
| [Alpha Vantage MCP](https://mcp.alphavantage.co/) | Acceso cómodo a un proveedor ya integrado | Herramienta del desarrollador | P1 opcional; no duplicar runtime |
| [Databento](https://databento.com/docs/api-reference-historical/symbology/symbology-resolve) | Timestamp/eventos/símbolos históricos y estimador de costos | Intradía/futuros/opciones como extensión | P2; no necesario para MVP diario |
| [OpenBB MCP](https://docs.openbb.co/odp/python/extensions/interface/openbb-mcp) | Exploración multifuente y herramientas dinámicas | Sidecar de investigación con versión fijada | P2; evitar dependencia redundante |
| [Alpaca CLI](https://docs.alpaca.markets/us/docs/alpacas-cli) | Diagnóstico y scripts JSON | Herramienta operativa de piloto | P2; alpha preview |
| [IBKR](https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction) | Acceso a cuenta y datos con permisos existentes | Futuro broker adapter | P3; sólo si objetivo/cuenta lo justifican |

## Costos y licencias que cambian la decisión

[Alpaca](https://docs.alpaca.markets/us/docs/about-market-data-api) publica Basic gratuito con realtime IEX, frente a Algo Trader Plus de USD 99/mes con bolsas US completas. No comparar barras de feeds diferentes como si fueran idénticas. Son planes Trading API; un SaaS multiusuario requiere revisar sus condiciones propias.

[Alpha Vantage](https://www.alphavantage.co/support/) publica 25 requests/día gratis, con una excepción para proyectos abiertos o educativos verificados. La existencia del repositorio no confirma elegibilidad ni aprobación. MCP comparte restricciones del servicio.

[Massive MCP](https://www.massive.com/docs/ai-tools/quickstart) conserva los permisos del plan; Databento ofrece estimación por petición, cuyo costo final depende de los bytes enviados. No se verificaron precios de planes Massive, Financial Datasets ni tarifas de bolsas Databento/IBKR: no asignar un presupuesto numérico inventado. API, código open source y derechos para guardar/redistribuir datos son tres cosas distintas.

## Diseño de integración propuesto

1. Establecer un sobre de datos: `vendor`, `dataset/feed`, `instrument_id`, `event_time`, `available_at`, `as_of`, `retrieved_at`, `adjustment_mode`, `currency/unit`, `source_url`, `raw_payload_hash` y restricciones conocidas de uso. Es propuesta, no inventario de campos existentes.
2. Mantener el router y sus errores explícitos. Una suscripción ausente, throttle o respuesta vacía no significa que no exista el instrumento. No permitir fallback silencioso a otro feed. Además, `agents/tools.py` llama directamente `build_verified_market_snapshot`, cuyo `vendors/yahoo/snapshot.py` importa `yahoo.ohlcv.load_ohlcv`: añadir un vendor al router NO migra ese snapshot. Hacer el snapshot neutral al proveedor y revisar también `memory/settlement.py` antes de comparar señales y resultados; de otro modo podrían mezclarse feeds dentro del mismo análisis.
3. Comparar Massive y Alpaca sobre un conjunto pequeño: acción líquida, split, cambio de símbolo, símbolo deslistado, festivo y sesión incompleta. Medir cobertura, discrepancia, latencia y costo por análisis, incluyendo las llamadas inducidas por el LLM.
4. Comparar Financial Datasets con SEC usando filing posterior al período fiscal y una enmienda. Aplicar cutoff de publicación, no sólo `report_period_lte`. Verificar si devuelve las versiones originales y cómo resuelve filas revisadas; la documentación de [income statements](https://docs.financialdatasets.ai/api/financials/income-statements) aporta filtros y provenance, pero no prueba sola todo el comportamiento PIT.
5. Para macro, mantener vintage pinning y probar que un dato revisado no cambia una ejecución histórica. Para intradía, añadir timezone, horario de publicación y cutoff exacto.
6. MCP para investigación y acceso asistido; SDK/API con schemas estables para el camino reproducible. La elección es arquitectónica: un servidor MCP no garantiza fechas correctas, deduplicación, presupuesto ni trazabilidad.

## Skills y documentación que sí aportan

Crear un skill del proyecto que reúna las invariantes ya presentes: precios ajustados/no ajustados, fecha fiscal frente a publicación, unidades/monedas, identidad del instrumento, sesión bursátil y vendor explícito. La guía [Massive](https://www.massive.com/docs/ai-tools/quickstart) respalda esa práctica, pero no es evidencia de un paquete oficial de Skills instalable. Evitar confundir una recomendación de crear SKILL.md con un catálogo existente.

Agregar referencias curadas a docs y llms.txt en lugar de copiar documentación masiva al prompt. Para OpenBB distinguir docs V5 y V4; Workspace MCP necesita browser conectado y es distinto al MCP server Python. Para Alpaca CLI fijar versión y mantener pruebas de contrato porque el proveedor lo marca Alpha Preview.

## Criterio de aceptación de un piloto

El recurso aporta valor sólo si mejora cobertura o verificación frente a Yahoo/Alpha Vantage/SEC/FRED, respeta el cutoff temporal, proporciona errores distinguibles, deja una ruta al dato original y tiene costo/permiso de uso aceptables. No instalar todos los MCPs: escoger uno de datos de mercado y uno de documentación/investigación, medirlos, y conservar únicamente los que superen esos criterios.

Los 12 archivos `sources/data_*.md` contienen URL individual, fecha, extracto breve, valoración y límites. La fecha de consulta no demuestra la fecha de publicación; donde no está visible se declara desconocida.
