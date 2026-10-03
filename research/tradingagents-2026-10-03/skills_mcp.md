# Skills, MCP, documentación y CLI para TradingAgents

Investigación consultada el 2026-10-03. Diez fuentes primarias, fichas `sources/skills_*.md`. Se verificó disponibilidad documental; no se instalaron paquetes ni se probaron servidores autenticados. Prioridades y esfuerzo son valoración técnica, no benchmarks.

## Encaje observado en el repositorio

El checkout ya contiene `tradingagents/backtest.py`, `portfolio.py`, proveedores SEC EDGAR/FRED/Reddit/Stocktwits/Polymarket y un router de proveedores. Por tanto, no procede presentar esos dominios como ausencias universales. `agents/tools.py` inyecta símbolo y fecha desde estado y limita fechas mediante `as_of_window`; `graph/setup.py:85` crea `ToolNode(list(spec.tools))` y `agents/analysts/turn.py` enlaza las herramientas mediante `llm.bind_tools`. Es una base natural para herramientas adaptadas desde MCP, pero conectarlas sin envoltorio puede perder restricciones temporales y de símbolo ya existentes.

La distinción operativa es esencial: **skills del agente desarrollador** mejoran cómo mantenemos el repositorio; **skills financieras** aportan procedimientos analíticos; **MCP runtime** incorpora herramientas al proceso Python. Añadir `SKILL.md` o configurar un MCP en Codex/Claude no lo vuelve disponible automáticamente a los analistas LangGraph.

## Selección priorizada

| Recurso | Tipo / origen | Aporte concreto | Prioridad / esfuerzo estimado | Límite y decisión |
|---|---|---|---|---|
| [LangChain Docs + Reference MCP](https://docs.langchain.com/use-these-docs) | Desarrollo; oficial | Guías LangGraph y firmas precisas de SDK al editar `graph/`, `llm_clients/` y herramientas | P0 / bajo | Dos endpoints complementarios. No son datos financieros ni herramienta del analista. |
| [uv](https://docs.astral.sh/uv/) | CLI desarrollo; oficial Astral | Entorno reproducible con lockfile y ejecución de pytest/ruff ya configurados | P0 / bajo-medio | Resolver y validar versiones locales; los mínimos `>=` no son un lock. No instalar últimas versiones sin evaluar. |
| [Anthropic Financial Services](https://github.com/anthropics/financial-services) | Skills financieras; oficial Anthropic | `financial-analysis`: DCF/comparables/modelado; `equity-research`: earnings, tesis, catalizadores | P1 / medio | Apache-2.0. Material orientado a Claude: adaptar reglas y rúbricas, conservar atribuciones; no asumir plug-and-play con LangGraph. |
| [Agent Skills specification](https://agentskills.io/specification) | Estándar | Empaquetar procedimientos propios con metadatos, referencias y scripts | P1 / bajo | No es un framework financiero. `allowed-tools` es experimental, no sustituye controles Python. |
| [LangChain MCP adapters](https://github.com/langchain-ai/langchain-mcp-adapters) | Integración runtime; oficial | Convertir herramientas de servidores MCP en herramientas LangChain | P1 / medio | Dependencia opcional, lista explícita por analista y envoltorio que preserve fecha/símbolo, errores y trazabilidad. |
| [MCP Inspector](https://github.com/modelcontextprotocol/inspector) | CLI/UI desarrollo; proyecto MCP | Pruebas de contrato: conectar, listar, ejecutar, comprobar esquema/errores | P1 / bajo | README actual corresponde a v2; no copiar comandos de v1. Evitar datos reales en pruebas iniciales. |
| [Context7](https://github.com/upstash/context7) | MCP o CLI+skill; Upstash | Consultar documentación versionada de librerías del proyecto con `ctx7 library` y `ctx7 docs` | P1 / bajo | Índice comunitario y backend privado. Verificar respuesta contra docs primarias; API key recomendada, límites por servicio. |
| [GitHub MCP](https://github.com/github/github-mcp-server) | Desarrollo; oficial GitHub | Analizar issues/PRs upstream, incompatibilidades y revisión de cambios | P2 / bajo | Configurar sólo toolsets necesarios y lectura para investigación; no requiere estar dentro del runtime financiero. |
| [Alpaca MCP](https://github.com/alpacahq/alpaca-mcp-server) | Datos/ejecución; oficial Alpaca | Explorar datos y, en una fase separada, paper trading | P2 / medio-alto | Cuenta/keys; v2 cambió interfaces. Servidor incluye acciones sobre órdenes: no incorporarlas al catálogo de analistas. README advierte falta de autenticación remota propia. |
| [MCP Registry](https://github.com/modelcontextprotocol/registry) | Descubrimiento; proyecto MCP/comunidad | Localizar paquetes y verificar identidad del namespace antes de selección | P2 / bajo | Un registro no certifica calidad ni seguridad. Su README conserva status de 2025: no afirmar GA actual con esa evidencia. |

## Skills que sí conviene adaptar

El repositorio de Anthropic ofrece una base real para procedimientos de comparables, DCF y seguimiento de resultados/trabajo de equity research. Elegir componentes pequeños de `financial-analysis` y `equity-research`, frente a importar agentes enteros que dupliquen el grafo. Los conectores empresariales enumerados allí pueden exigir suscripciones; que aparezcan en el plugin no concede acceso a FactSet, Morningstar, S&P o LSEG. [Fuente primaria](https://github.com/anthropics/financial-services).

Propuestas de skills propias — **a crear, no hallazgos de paquetes ya existentes**:

- `tradingagents-provider-contract`: registrar vendor en router, comprobar límites as-of, faltantes, cuotas y procedencia.
- `tradingagents-research-review`: verificar fuentes de tesis, separar hechos de hipótesis y comparar salida con datos determinísticos.
- `tradingagents-backtest-audit`: revisar información disponible en fecha, costos, benchmark, splits y reproducibilidad.
- `tradingagents-release-check`: ejecutar las comprobaciones existentes, registrar lock y revisar compatibilidad de clientes LLM.

El formato estándar permite instrucciones y recursos cargados gradualmente; una skill es procedimiento, no garantía de corrección ni barrera de autorización. [Especificación](https://agentskills.io/specification).

## Diseño recomendado de una primera integración MCP

Inferencia de ingeniería a partir del código local: conservar la interfaz `agents/tools.py → dataflows/router.py → vendor` y añadir un proveedor MCP opcional detrás del router cuando el servidor proporcione una capacidad verdaderamente nueva. Mantener las mismas reglas de fecha y símbolo; normalizar respuesta, proveedor, hora de consulta y fecha de publicación. `ToolNode` debería recibir el catálogo mínimo por rol. La adaptación de herramientas está soportada por el [proyecto oficial LangChain MCP adapters](https://github.com/langchain-ai/langchain-mcp-adapters), pero su compatibilidad exacta requiere una prueba con las dependencias locales.

Criterios de aceptación de la prueba: servidor falso controlado, respuesta fuera de fecha rechazada, timeout convertido al error de vendor existente, esquema estable, ausencia de herramientas de órdenes y resultado rastreable. Usar Inspector para validar protocolo y tests Python para validar las invariantes específicas de TradingAgents. Un MCP no añade por sí solo datos point-in-time ni elimina filtración de información futura.

## Orden de adopción sugerido

1. Docs LangChain + Reference en el entorno del desarrollador y lock reproducible.
2. Adaptar una skill de earnings o revisión de tesis y medir exactitud/cobertura de citas sobre casos ya conocidos.
3. Probar un solo proveedor MCP con datos de lectura y las mismas restricciones del router.
4. Evaluar datos empresariales sólo si aportan cobertura/campos/licencias que los proveedores actuales no resuelven.
5. Considerar Alpaca paper en un módulo separado si el objetivo del proyecto incluye ejecución simulada.

Ninguna fuente revisada demuestra una mejora de rentabilidad para este checkout. La utilidad propuesta es documentación más precisa, análisis trazable, interoperabilidad y reproducibilidad.
