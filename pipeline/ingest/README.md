# ingest — un módulo por fuente

Pide cada fuente, guarda la respuesta cruda y dice en qué estado quedó. **No inventa nada**: una fuente que no llega queda «por integrar» o «sin dato», nunca con un valor de relleno.

## Módulos

| Archivo | Qué hace | Estado |
|---|---|---|
| `contract.py` | Errores (`SourcePending`, `SourceError`), procedencia, `Series`, nivel de soporte, píxeles limpios y `contract_value` (valida contra `shared/schema/`). | Hecho |
| `http.py` | Única salida a la red: reintentos, caché por respuesta, secretos a salvo. | Hecho |
| `power.py` | NASA POWER, clima diario (región). | Hecho, probado en vivo |
| `openmeteo.py` | Open-Meteo / ERA5, contraste de lluvia y ET0. Externa a la NASA. | Hecho, probado en vivo |
| `soilgrids.py` | SoilGrids, suelo a 250 m. Externa a la NASA. | Hecho; **sin valores en el punto de ejemplo** |
| `stac.py` | Escenas HLS (CMR-STAC) y Sentinel-2 (Earth Search), solo metadatos. | Hecho, probado en vivo |
| `cmr.py` | Descubre productos de la NASA y sus versiones. | Hecho |
| `credentialed.py` | IMERG, NASADEM, MODIS, SMAP, ECOSTRESS, GRACE y ERA5-Land. | **Esqueletos**: sin token dicen «falta …»; con token, «por integrar». |
| `earthdata.py`, `access.py` | Comprueba el acceso con token a IMERG, NASADEM, MODIS y HLS (ver «Acceso con token»). | Hecho; acceso confirmado |
| `env.py` | Lee las credenciales de la variable de entorno o del `.env`. | Hecho |
| `catalog.py` | Catálogo de las 12 fuentes (es un dato). | Hecho |
| `load.py` | Corre cada conector, fija su estado y deja el manifiesto en bronce. | Hecho |
| `eda.py` | El análisis exploratorio: cobertura, calidad, estacionalidad, consistencia, soporte, balance de agua y plan de degradación. | Hecho |
| `run.py` | La línea de comandos. | Hecho |

Solo usa la biblioteca estándar y NumPy: no agrega dependencias.

## Cómo se corre

```bash
cd pipeline
.venv/bin/python -m ingest.run --lon -89.42 --lat 20.30        # punto de ejemplo cerca de Oxkutzcab
.venv/bin/python -m ingest.run --lon -89.42 --lat 20.30 --only power,openmeteo
```

El punto es obligatorio: el polígono de la parcela de ejemplo aún no está elegido y nadie lo inventa. La primera corrida tarda unos 2 minutos (SoilGrids es lento); la segunda sale de la caché. Deja:

- `data/bronze/<parcela>/<fuente>/manifest.json` y las respuestas guardadas de esa fuente,
- `data/eda/<parcela>/eda_report.json`, `eda_report.md` y `sources.json`.

`data/` no se versiona. Las credenciales se leen de `EARTHDATA_TOKEN`, `CDS_API_KEY` e `INEGI_TOKEN`; sin ellas, esas fuentes quedan «por integrar».

## Acceso con token de Earthdata

IMERG, NASADEM, MODIS y los píxeles de HLS necesitan un token de [Earthdata Login](https://urs.earthdata.nasa.gov/) (menú «Generate Token»; vence a los ~60 días). Se guarda en el `.env` de la raíz, que git ignora, o en la variable de entorno `EARTHDATA_TOKEN`:

```bash
cp .env.example .env          # y complete EARTHDATA_TOKEN (nunca suba el .env)
cd pipeline
.venv/bin/python -m ingest.access                    # los cuatro productos
.venv/bin/python -m ingest.access --only imerg,hls   # solo algunos
```

Por cada producto busca en CMR (abierto) un granulo que cruce el punto, pide **solo los primeros 64 KB** de su archivo con `Authorization: Bearer` y comprueba que lo recibido es el archivo (por su firma de formato: HDF5, ZIP, HDF4 o TIFF) y no la página de inicio de sesión, que también responde 200. Repite cada prueba **sin token** como control. Deja `data/access/access_report.json`.

- El token viaja **solo a dominios de la NASA y por HTTPS** (`*.earthdata.nasa.gov`, `*.earthdatacloud.nasa.gov`). Los servidores redirigen a CloudFront o S3 con una URL firmada, que rechaza la petición si además lleva `Authorization`: el encabezado se quita en ese salto.
- Nunca se imprime, ni se guarda en la caché, el informe, los mensajes de error ni git. Se comprueba con pruebas.
- Si un producto responde 401 o 403 con un token válido, suele faltar autorizar la aplicación en el perfil de Earthdata (Applications → Authorized Apps), por ejemplo «NASA GESDISC DATA ARCHIVE» para IMERG.
- Esto confirma el acceso; **no es todavía el conector**. Leer el valor del punto (celda de IMERG, píxel de MODIS y HLS, elevación de NASADEM) es el siguiente paso y necesitará leer HDF5, HDF4 y GeoTIFF.

## Manifiesto de bronce

```json
{
  "source": "HLS (NASA LP DAAC)",
  "product": "HLSL30_2.0+HLSS30_2.0",
  "parcel": "yuc-demo-001",
  "requested": {"start": "2016-01-01", "end": "2025-12-31"},
  "retrieved_at": "2026-11-15T13:31:09Z",
  "status": "ok",
  "files": ["<respuesta guardada>.json"],
  "notes": []
}
```

`status` es `ok`, `pending` (falta una credencial o el conector es un esqueleto) o `no_data` (la fuente respondió con error, no respondió o no tiene valores). De los manifiestos sale el campo `provenance` de cada `ContractValue`.

## Reglas ante fallos (ARQUITECTURA-DEV §4.1)

- **Reintentos con espera creciente** (2, 4, 8, 16 s, con algo de aleatoriedad) ante 429, 502, 503 y 504 y ante fallos de red. **No** se reintentan 400, 401, 403 ni 404.
- **Reanudable:** toda petición pasa por la caché de su fuente; una segunda corrida no vuelve a pedir lo que ya tiene.
- **Falla una fuente, sigue el sistema:** al agotar reintentos, `no_data`, y el paquete la declara «sin dato» (`value: null`). Nunca se rellena.
- **Un 200 con todo nulo es «sin dato», no «ok»** (SoilGrids lo hace en el punto de ejemplo).
- **Sin evadir límites:** nada de rotar IP ni disfrazar el cliente. POWER advierte que pedir muchas veces lo mismo puede bloquear: se pide un año por vez y se guarda.
- **El token** va en la variable de entorno; nunca en el repositorio, en la caché, en el informe ni en los mensajes de error.
- **Solicitudes asíncronas** (IMERG, ERA5-Land): pendientes. Se enviará una vez, se guardará el identificador de la tarea y se consultará a intervalos crecientes.

## Cuidados con CMR-STAC (HLS)

- Las colecciones `HLSL30_VI_2.0` y `HLSS30_VI_2.0` (índices de vegetación) repiten las **mismas escenas**: se piden solo `HLSL30_2.0` y `HLSS30_2.0`, y se descartan repetidas por clave de escena.
- El servidor responde **502 si la página pesa más de ~1 MB** (cada escena ocupa ~12 KB): `limit=100` falla y `75` responde. Se piden 50 por página.
- El listado de colecciones y los resultados vienen paginados: se sigue el enlace `next`.
- Los identificadores cambian (`HLSL30.v2.0` → `HLSL30_2.0`): se descubren, no se fijan.

## Pruebas

Corren sin red (`pytest` desde `pipeline/`): `tests/test_ingest.py` y `tests/test_eda.py` usan las respuestas grabadas de `tests/fixtures/` (con la forma real de cada servicio), un transporte falso y datos sintéticos solo como entrada. Incluyen **una fuente que falla a propósito**: se reintenta, se registra «sin dato» y el sistema sigue.

Los hallazgos de la primera corrida real están en [`docs/EDA-hallazgos.md`](../../docs/EDA-hallazgos.md).
