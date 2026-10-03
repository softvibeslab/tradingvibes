# F3: simulación como capa externa

Estado: capacidad ausente en el evaluador local; desempeño no probado.

Evidencia local: docstring de backtest.py excluye simulación de cartera; portfolio.py sólo recibe contexto.

Fuentes: [vectorbt](../sources/eval_vectorbt.md), [LEAN](../sources/eval_lean.md), [Nautilus](../sources/eval_nautilus.md).

Acción: exportar señales fechadas y escoger un motor cuando ejecución sea objetivo. Definir sizing, cash, fees, fill posterior a decisión y benchmark.

Límite: tres motores independientes pero fuentes del mismo tipo (documentación); no se cumple triangulación de tres tipos, ni paper equivale a real.
