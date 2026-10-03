# OpenBB MCP Python V5

- URL: https://docs.openbb.co/odp/python/extensions/interface/openbb-mcp
- Consultado: 2026-10-03.
- Fecha de publicación/revisión: No indicada; documentación V5.
- Tipo: documentación oficial; extracción web, sin ejecutar servicio.
- Cita breve: “The tools come from whatever provider and extension packages are installed alongside it.”

Primaria oficial; confianza alta. openbb-mcp expone FastAPI, búsqueda dinámica y pipeline; requiere Python >=3.10/openbb-core 2.x. Útil para investigación transversal y prototipo de providers; no añadir agregador como dependencia obligatoria si sólo duplica FRED/SEC/Yahoo. Contrastar V4/V5 y fijar versiones. Proveedor subyacente conserva claves/costos/licencias. Workspace MCP es producto distinto con sesión browser activa. Prioridad P2.
