# Evaluación, reproducibilidad y observabilidad

Consulta: 2026-10-03. Revisión estática y documentación primaria; no instalación, ejecución de pruebas ni cambios al código. Las prioridades y esfuerzos son estimaciones, no resultados de un benchmark.

## Lo que ya existe y cambia la recomendación

- `tradingagents/backtest.py:1` declara deliberadamente un evaluador de decisiones, no simulador de cartera. `run_backtest` usa una instancia del grafo, un log aislado por ejecución, reanudación por ticker/fecha y el mismo PortfolioContext en cada celda. Por ello añadir LEAN como reemplazo directo sería un cambio de producto innecesario.
- `backtest.py:115` reconoce una sola muestra de modelo por celda y feeds textuales no archivados. `summarize` calcula aciertos direccionales y alpha medio por rating; `_alpha` recupera porcentajes redondeados a 0.1 puntos porcentuales. No equivale a retorno ejecutable ni significancia estadística.
- `memory/log.py:81` ya filtra lecciones por `resolved <= as_of`; `tests/test_memory_pointintime.py` cubre lecciones futuras y entradas legadas. `tests/test_statement_knowledge_time.py` comprueba bloqueo histórico de estados Yahoo/Alpha Vantage sin fecha de publicación y prioridad SEC. No recomendar volver a implementar estos controles.
- `portfolio.py:1` es contexto aportado por el usuario, sin ledger ni fills. `memory/settlement.py` calcula retorno entre cierres y benchmark; datos no disponibles permanecen pendientes. Excluir pendientes puede introducir selección si se concentran en activos deslistados: hipótesis que requiere medir, no fallo probado.
- `graph/trading_graph.py:59` acepta callbacks; hay punto natural de instrumentación. `pyproject.toml` declara rangos mínimos amplios; la búsqueda de archivos no encontró uv.lock/poetry.lock. Esto dificulta reproducir entornos; no demuestra vulnerabilidades.

## Herramientas con valor y encaje

| Prioridad | Recurso | Aporte concreto / integración propuesta | Esfuerzo estimado / límite |
|---|---|---|---|
| P0 | [LangSmith Evaluation](https://docs.langchain.com/langsmith/evaluation) | Dataset fijo ticker/fecha/evidencias; experimentos repetidos; evaluadores por código, revisión humana y comparación de versiones. Aprovechar LangChain y callbacks. | 2–4 días para piloto; cloud/retención y costes deben decidirse; no acredita rentabilidad. |
| P0 alternativa | [Phoenix](https://arize.com/docs/phoenix) | Traces OpenTelemetry/OpenInference, datasets y experimentos; encaja con ejecución local y LangChain. Dispone de CLI y skills de coding agents documentadas. | 2–4 días; probar una plataforma, no tres. Trazar proveedores externos requiere redacción de secretos y políticas de datos. |
| P1 alternativa | [Langfuse](https://langfuse.com/docs/evaluation/overview) | Scores, datasets, evaluadores de código y experimentos CI con umbrales. Útil si ya se opera Langfuse. | 2–4 días; preferencia operativa, no ventaja financiera demostrada. |
| P0 | [uv lock/sync](https://docs.astral.sh/uv/concepts/projects/sync/) | Lockfile y ejecución CI con `--locked`, archivando Python/SO/config/modelo/commit. | Medio–1 día; lockfile reproduce dependencias, no respuestas LLM ni API remota. |
| P1 | [pip-audit](https://github.com/pypa/pip-audit) | Auditoría de dependencias resueltas en CI; alertas separadas del score financiero. | Medio día; detecta vulnerabilidades conocidas, no es analizador del código ni prueba de seguridad total. |
| P1, tras congelar señales | [vectorbt Portfolio](https://vectorbt.dev/api/portfolio/base/) | Consumir señales exportadas y fechadas; comparar sizing, fees, slippage y retraso hasta siguiente sesión. | 3–5 días; definir cash, divisa y rebalanceo antes; simulación vectorizada no garantiza ejecución real. |
| P2 | [QLib/qrun](https://qlib.readthedocs.io/en/latest/component/workflow.html) | Baseline cuantitativo con particiones train/valid/test, análisis de señales y registro de experimentos. | 1–2 semanas; otro framework sólo se justifica si se quiere un benchmark ML transversal. |
| P2 | [LEAN CLI](https://www.quantconnect.com/docs/v2/lean-cli/backtesting/deployment) | Adaptador externo de señales para backtests locales en Docker y resultados JSON; `lean backtest` documentado. | 1–2 semanas; acceso a datos, derechos y requisitos de cuenta/CLI necesitan validación antes de adoptar. |
| P2 | [NautilusTrader](https://nautilustrader.io/docs/latest/concepts/backtesting/) | Motor orientado a eventos con fill models, slippage, cuentas y margen; útil si aparece requerimiento de microestructura. | 2+ semanas; elevado coste para recomendaciones diarias; no instalar junto a LEAN sin necesidad. |

## Primer experimento propuesto

1. Congelar 30–50 casos de regresión con evidencia autorizada, `published_at`, `available_at`, `retrieved_at`, vendor, checksum, zona horaria y corte exacto. El número es un piloto operativo, no potencia estadística.
2. Registrar por run commit, entorno, prompt, versión/alias del modelo, temperatura, configuración, portfolio fingerprint y estado de memoria. Exportar el alpha numérico sin usar texto redondeado como almacén analítico.
3. Comparar grafo completo con market-only, sin memoria y baseline simple; repetir al menos tres veces para detectar variabilidad inicial, sin presentar tres repeticiones como validación estadística suficiente. Emparejar los mismos casos y evidencias.
4. Medir cumplimiento temporal, citas verificables, extracción numérica, rating válido, abstención, cobertura por vendor, coste, latencia y fallos. Separar estos criterios del retorno posterior.
5. Extender a walk-forward con ventana purgada/embargo acorde al horizonte y evaluación prospectiva. Separar tuning y test final; reportar incertidumbre por bloques temporales, no tratar observaciones solapadas como independientes.
6. Sólo tras lo anterior, exportar señales a un único simulador externo y especificar primera ejecución posterior a la decisión, costes, liquidez, short/borrow y corporate actions.

## Revisión adversarial

**“Ya tiene PIT, entonces el backtest es limpio.”** Los controles de memoria y estados financieros son reales, pero no eliminan conocimiento del futuro incorporado en los pesos del LLM. Un modelo actual puede conocer eventos históricos sin herramientas. La mitigación principal es evaluación prospectiva y declarar la limitación de retrospectivas; pedir “ignora el futuro” no prueba aislamiento.

**“Más agentes implican más alpha.”** Es una hipótesis; ablations y comparación por coste pueden favorecer una configuración simple. Un juez LLM puede premiar estilo y coincidir con su propio proveedor; usar reglas verificables y anotación humana.

**“Las celdas son independientes.”** Lo son respecto al estado de cartera, pero comparten memoria del run y fechas/retornos solapados. `run_backtest` itera ticker antes de fecha; la memoria cruzada disponible puede depender del orden. Debe ensayarse permutar tickers con memoria congelada y comparar; no se ha demostrado diferencia en ejecución.

**“Un lockfile y tracing dan reproducibilidad.”** Son necesarios pero insuficientes: snapshots de evidencia, respuestas y versiones del servicio faltan para replay exacto. SaaS eval no crea datos PIT.

**“El alpha medio demuestra estrategia rentable.”** El cálculo actual es retorno del activo menos benchmark, sin posición financiada ni costes; ratings bajistas no son P&L de venta corta. Publicar CAGR/Sharpe sobre estas celdas requeriría una cartera definida; ahora sería engañoso.

**“Instalemos todo.”** LangSmith, Phoenix y Langfuse cubren necesidades muy solapadas. Seleccionar una con dos casos reales y criterios de exportabilidad, overhead y operación. vectorbt/LEAN/Nautilus son alternativas de distinto alcance, no una lista acumulativa.
