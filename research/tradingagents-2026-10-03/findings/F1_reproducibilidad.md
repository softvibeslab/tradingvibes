# F1: priorizar evidencia y evaluación

Estado: recomendación de ingeniería, efecto en alpha no demostrado.

Evidencia local: backtest.py:115 reconoce feeds sin archivo y una muestra por celda; run_settings() guarda parte de la configuración; no hay lockfile encontrado.

Fuentes: [uv](../sources/eval_uv.md), [evaluación LangSmith](../sources/eval_langsmith.md), [DuckDB](../sources/core_03_duckdb.md), [sesgo temporal académico](../sources/core_05_lookahead.md).

Acción: manifiesto y replay de datos, después experimento emparejado. No confundir reproducibilidad del entorno con determinismo LLM.

Falsación: si una comparación controlada muestra que el costo de archivo/evaluación excede su beneficio para el uso elegido, reducir alcance. No se midió ROI.
