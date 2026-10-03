# FRED/ALFRED real-time periods

- URL: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- Consultado: 2026-10-03.
- Fecha de publicación/revisión: No indicada.
- Tipo: documentación oficial; extracción web, sin ejecutar servicio.
- Cita breve: “On almost all URLs, the default real-time period is today.”

Primaria oficial; confianza alta. realtime_start/end define lo conocido en una fecha histórica. Ya implementado y testeado en fred.py/test_fred.py. Valor incremental: registrar vintage y separar observation_date, publication_date y retrieval_time. No proponer duplicar integración. Prioridad P0 para contrato de datos; revisar derechos por serie antes de redistribuir.
