# Plan de investigación: TradingAgents

Fecha: 2026-10-03. Género: panorama tecnológico y decisión de adopción. Idioma: español.

## Decisión
Qué skills, documentación, MCP, APIs, bibliotecas y CLI agregan capacidad verificable al checkout local, y en qué orden incorporarlas.

## Hipótesis falsables
- H1. La mayor oportunidad inmediata está en reproducibilidad y evaluación, antes que en agregar agentes o modelos.
- H2. MCP agrega interoperabilidad, pero no sustituye las garantías temporales de los adaptadores actuales.
- H3. Un motor externo de simulación y paper trading añade capacidades ausentes del evaluador de decisiones local.
- H4. Las skills financieras aportan métodos reutilizables, pero requieren adaptación y no garantizan mejor desempeño.

## Método
Lectura estática del checkout `8b22d43d01d9ddda5d686d093d5385884622f3de`, arquitectura, contratos, pruebas y CI. Investigación paralela de datos/APIs, skills/MCP y evaluación/observabilidad; síntesis y revisión adversarial central. Priorizar documentación original, repositorios de autores y artículos académicos. Cada fuente se guarda con URL, extracto breve y valoración. Inspección de credenciales limitada a nombres en `.env.example`; no leer secretos ni operar cuentas.

## Criterios
Necesidad local demostrable, compatibilidad, temporalidad, mantenibilidad, costo y esfuerzo. Separar disponibilidad documentada de integración probada. Tres fuentes independientes de tipos diversos por tesis cuando existan; señalar evidencia insuficiente cuando no. Una capacidad específica se acredita con documentación primaria, sin fingir tres confirmaciones independientes del mismo proveedor.

## Búsqueda adversarial
Conocimiento futuro memorizado por LLM; noticias sin archivo; paper trading frente a ejecución real; MCP con escritura; duplicación de routers; costo operativo de observabilidad; procedencia de skills.

## Límites y cierre
No instalar ni modificar runtime. No certificar rentabilidad. No confundir filtrado diario con integridad intradía. Precios y licencias sujetos a mercado y uso. Entregar diagnóstico con rutas, matriz priorizada, fuentes, roadmap con aceptación, alternativas y protocolo de actualización. Cerrar con opciones verificadas para cada categoría solicitada y punto de integración para cada prioridad.

## Cierre ejecutado

Se inspeccionó código y CI; se guardaron 39 fichas de fuentes, tres informes temáticos, cuatro hallazgos y una síntesis. Revisión adversarial separada: MCP opcional, resolución uv sin probar, skills dependientes del host, PIT diario insuficiente para intradía y alternativas de observabilidad/simulación no acumulativas. Se reabrieron fuentes principales y condiciones de costos. Enlaces locales verificados. Sin ejecución de tests de runtime, instalaciones ni operaciones autenticadas. La triangulación de tres tipos independientes no se logró para todas las tesis y se declara en la síntesis.
