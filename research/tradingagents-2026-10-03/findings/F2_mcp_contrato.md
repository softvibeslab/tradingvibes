# F2: MCP no reemplaza el contrato de datos

Estado: alcance funcional respaldado; compatibilidad runtime pendiente.

Evidencia local: tools.py limita fecha/símbolo; router.py tipa fallos y fallbacks. snapshot.py y settlement.py aún usan Yahoo directamente.

Fuentes: [adapters](../sources/skills_03.md), [Massive](../sources/data_massive.md), [SEC](../sources/data_sec.md), [FRED](../sources/data_fred.md).

Acción: MCP opcional y de lectura detrás de validación. No sustituir una API existente sólo por cambiar transporte.

Aceptación: misma evidencia y restricciones con mock de protocolo y tests de fechas/errores; integración autenticada todavía no probada.
