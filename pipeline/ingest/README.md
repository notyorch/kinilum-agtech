# ingest — un módulo por fuente

Un módulo por fuente (`power.py`, `gpm.py`, `hls.py`, `modis.py`, `smap.py`, `srtm.py`, `ecostress.py`). **Orden de trabajo, el de mayor riesgo primero:** HLS y MODIS (hacen fila en los servidores de la NASA), luego GPM y SMAP, luego POWER y SRTM, al final ECOSTRESS.

## Qué debe dejar cada módulo (bronce)

`data/bronze/<parcela>/<fuente>/` con la respuesta cruda y un `manifest.json`:

```json
{
  "source": "GPM IMERG",
  "product": "GPM_3IMERGM v07",
  "parcel": "yuc-demo-001",
  "requested": {"start": "2000-06-01", "end": "2026-10-31"},
  "retrieved_at": "2026-11-14T18:20:00Z",
  "status": "ok",
  "files": ["..."],
  "notes": []
}
```

`status` es `ok` o `no_data`. De los manifiestos sale el campo `provenance` de cada `ContractValue`.

## Reglas ante fallos (ARQUITECTURA-DEV §4.1)

- **Reintentos con espera creciente** (2, 4, 8, 16 s, con algo de aleatoriedad) ante 429, 502, 503 y 504. **No** se reintentan 400, 401 ni 404.
- **Solicitudes asíncronas:** se envía una vez, se guarda el identificador de la tarea y se consulta a intervalos crecientes. No falla porque la tarea siga en proceso.
- **Reanudable:** antes de pedir, se revisa si ya existe en bronce con la misma fuente, parcela y rango de fechas.
- **Falla una fuente, sigue el sistema:** al agotar reintentos, `status: "no_data"` y el paquete la declara «sin dato» (`value: null`). Nunca se rellena.
- **Sin evadir límites:** nada de rotar IP ni disfrazar el cliente.
- **El token** (`EARTHDATA_TOKEN`) va en la variable de entorno; nunca en el repositorio, ni en la imagen, ni en la app.

## Pruebas

Con respuestas simuladas en `tests/fixtures/` (con la forma que documenta cada servicio), incluida **una fuente que falla a propósito**: el pipeline debe reintentar, registrar «sin dato» y seguir.
