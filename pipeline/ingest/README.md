# ingest — un módulo por fuente

Pide cada fuente, guarda la respuesta cruda y dice en qué estado quedó. **No inventa nada**: una fuente que no llega queda «por integrar» o «sin dato», nunca con un valor de relleno.

## Módulos

| Archivo | Qué hace | Estado |
|---|---|---|
| `contract.py` | Errores (`SourcePending`, `SourceError`), procedencia, `Series`, nivel de soporte, píxeles limpios y `contract_value` (valida contra `shared/schema/`). | Hecho |
| `http.py` | Única salida a la red: reintentos, caché por respuesta, secretos a salvo. | Hecho |
| `power.py` | NASA POWER, clima diario (región). | Hecho, probado en vivo |
| `openmeteo.py` | Open-Meteo / ERA5, contraste de lluvia y ET0. Externa a la NASA. | Hecho, probado en vivo |
| `soilgrids.py` | SoilGrids, suelo a 250 m. Externa a la NASA. Si el punto no trae valores, busca la celda válida más cercana (250, 500 y 1,000 m) y lo dice. | Hecho, probado en vivo |
| `stac.py` | Escenas HLS (CMR-STAC) y Sentinel-2 (Earth Search), solo metadatos. | Hecho, probado en vivo |
| `cmr.py` | Descubre productos de la NASA y sus versiones. | Hecho |
| `imerg.py` | GPM IMERG Final diario: la celda del punto, día por día, por OPeNDAP. | Hecho, probado en vivo |
| `nasadem.py` | NASADEM: elevación y pendiente de los píxeles limpios de la parcela. | Hecho, probado en vivo |
| `smap.py` | SMAP L4: humedad del suelo de la celda de 9 km, un granulo por día, por OPeNDAP. | Hecho, probado en vivo |
| `cog.py`, `geo.py` | Lector mínimo de GeoTIFF en la nube por rangos (teselas, deflate, UTM propia con serie de Krüger) y las celdas completas dentro de la parcela. | Hecho; validado contra rasterio y PROJ |
| `vegetation.py`, `cover.py` | NDVI de la parcela escena por escena (HLS con Fmask; Sentinel-2 de respaldo con SCL) para todo el periodo. Fuente derivada `hls_ndvi`. | Hecho, probado en vivo |
| `credentialed.py` | MODIS, ECOSTRESS, GRACE y ERA5-Land. | **Esqueletos**: sin token dicen «falta …»; con token, «por integrar». |
| `earthdata.py`, `access.py` | Comprueba el acceso con token a IMERG, NASADEM, MODIS y HLS (ver «Acceso con token»). | Hecho; acceso confirmado |
| `env.py` | Lee las credenciales de la variable de entorno o del `.env`. | Hecho |
| `catalog.py` | Catálogo de las 13 fuentes (es un dato). | Hecho |
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
- Esto confirma el acceso. IMERG, NASADEM, SMAP y los píxeles de HLS ya leen valores (secciones siguientes); los píxeles de MODIS siguen pendientes y necesitarán leer HDF4.

## IMERG y NASADEM: cómo se leen

**IMERG.** El archivo diario global pesa ~28 MB y diez años serían más de 100 GB, así que no se descarga: se le pide al servidor OPeNDAP **solo la celda del punto** de cada día (3,653 peticiones pequeñas para 2016–2025, de 20 a 40 minutos con 4 simultáneas; `--workers` lo cambia). Es reanudable: cada respuesta queda en la caché y una segunda corrida no vuelve a pedir nada.

- Los corchetes de la selección van **codificados** (con corchetes crudos el servidor responde 400); las variables se separan con `;`; y una selección de **una sola celda devuelve el CSV vacío** (no es «cero»): se piden dos.
- La celda es la que **contiene** el punto (borde inferior incluido) y la otra es la vecina en latitud del lado del borde más cercano. El punto de ejemplo (20.30° N) cae **exactamente en el borde** entre dos celdas; el informe incluye el contraste con la vecina y un aviso si el punto está a menos de 0.02° del borde.
- La corrida Final tarda hasta ~4 meses en publicarse: los días recientes no existen y quedan sin dato; el informe lo dice.

**NASADEM.** Se descarga el tile de 1° × 1° (~7 MB, `.hgt` en un ZIP) con el token y se lee con la biblioteca estándar y NumPy: sin dependencias nuevas. La elevación y la pendiente (método de Horn) salen de los píxeles **completos** dentro de la parcela una vez descartado el borde de 30 m. Con una parcela de 200 m son entre 9 y 16 píxeles según cómo caiga la cuadrícula, no siempre los 16 de la fórmula. En terreno casi plano, un escalón de un metro entre píxeles de 30 m ya son ~3 % de pendiente: la pendiente tiene un piso de ruido y conviene leerla por clases, no por décimas.

**SMAP L4.** Cada granulo (cada 3 horas) pesa ~143 MB: se pide solo la celda del punto y **un granulo por día** (el de las 16:30 UTC), un año completo son ~365 peticiones. La malla (EASE-Grid 2.0 de 9 km) no es lat/lon: el índice de la celda se **estima con la fórmula de la proyección y se comprueba leyendo `cell_lat` y `cell_lon` del propio archivo**; si la celda más cercana queda a más de 7 km, se rechaza (una fórmula equivocada no puede dar una celda equivocada en silencio). Misma regla de OPeNDAP que IMERG: ventana de al menos 2 × 2 celdas.

**Del dato al contrato.** `harmonize/values.py` construye los valores del contrato (criterios en `harmonize/README.md`): `rain_season` (IMERG), `slope` (NASADEM), `tmax_may` (POWER), `soil_moisture_rootzone` (SMAP) y `root_depth` (lo declara el técnico) y `days_without_green_cover` (HLS). `run.py` escribe `data/gold/<parcela>/values.json` cuando están los seis, y `green_cover.json` con la clase de cada mes; si falta alguno, deja `values.partial.json`, que **no** es el del paquete. Con muy pocos años o días, el valor sale sin dato.

**Plantas verdes (HLS).** `cog.py` lee GeoTIFF en la nube por rangos HTTP (solo las teselas que cubren la parcela, tras descartar 30 m de borde) y `vegetation.py` calcula el NDVI por escena con la máscara Fmask; `cover.py` lo hace para todas las escenas del mosaico del punto y completa con Sentinel-2 (SCL) los meses sin escena limpia. El lector se validó contra rasterio y PROJ en una escena nueva y una vieja (proyección «definida por el usuario»); esas herramientas no son dependencias del proyecto.

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

El notebook de exploración, con el error E8 corregido, está en `pipeline/notebooks/kinilum_eda_00.ipynb` (sin salidas; corre en Colab o en local).

## Cuidados con CMR-STAC (HLS)

- Las colecciones `HLSL30_VI_2.0` y `HLSS30_VI_2.0` (índices de vegetación) repiten las **mismas escenas**: se piden solo `HLSL30_2.0` y `HLSS30_2.0`, y se descartan repetidas por clave de escena.
- El servidor responde **502 si la página pesa más de ~1 MB** (cada escena ocupa ~12 KB): `limit=100` falla y `75` responde. Se piden 50 por página.
- El listado de colecciones y los resultados vienen paginados: se sigue el enlace `next`.
- Los identificadores cambian (`HLSL30.v2.0` → `HLSL30_2.0`): se descubren, no se fijan.

## Pruebas

Corren sin red (`pytest` desde `pipeline/`): `tests/test_ingest.py` y `tests/test_eda.py` usan las respuestas grabadas de `tests/fixtures/` (con la forma real de cada servicio), un transporte falso y datos sintéticos solo como entrada. Incluyen **una fuente que falla a propósito**: se reintenta, se registra «sin dato» y el sistema sigue.

Los hallazgos de la primera corrida real están en [`docs/EDA-hallazgos.md`](../../docs/EDA-hallazgos.md).
