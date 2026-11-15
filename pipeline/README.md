# pipeline — datos de la NASA → paquete de la parcela

Corre **por lotes, antes de la demo**; nunca en vivo. Descarga datos, los armoniza, simula las rotaciones y deja **un JSON por parcela** que la app consume sin señal. Contrato: [`../shared/schema/`](../shared/schema/README.md). Arquitectura: [`../docs/ARQUITECTURA-DEV.md`](../docs/ARQUITECTURA-DEV.md).

Python **3.14** (`../.python-version`). Mientras no lleguen los datos de la NASA, se escribe y se prueba contra respuestas simuladas en `tests/fixtures/` y contra el paquete de ejemplo.

## Estado por módulo

| Carpeta | Dueño | Estado |
|---|---|---|
| `common/` | Jorge | **Hecho.** Carga y valida contra `shared/schema/`. |
| `package/` | Jorge | **Hecho, con pruebas.** `build.py` arma, valida y publica; `validate.py` valida. |
| `simulate/` | Jorge | **Esqueleto.** Definidos escenarios, grilla y codificación de puntajes para E0–E5, y la lectura del catálogo (`crops.py`: perfil por cultivo y variante, nitrógeno, criterios sin dato); `run.py` es **PENDIENTE** (no inventa resultados). |
| `ingest/` | Isis | **Sin empezar.** Ver `ingest/README.md` para el contrato de salida y las reglas de fallos. |
| `harmonize/` | Isis / Jorge | **Sin empezar.** Ver `harmonize/README.md`. |
| `rules/` | Jorge (con técnico) | **Catálogo `crops.v1.yaml`:** frijol (variantes xpelón, ib y negro), garbanzo, sorgo y trigo, con sus reglas de restricción. Todos los parámetros siguen «por definir» y todo está «a validar». |
| `Dockerfile` | Isis | **Pendiente.** Imagen `python:3.14-slim` fijada por *digest*, usuario sin privilegios, token solo en tiempo de ejecución. |
| `data/` | — | **No se versiona** (`.gitignore`): bronce / plata / oro. |

## Capas y qué deja cada paso

```
ingest      →  data/bronze/<parcela>/<fuente>/…     respuesta cruda + fecha + versión (de ahí sale `provenance`)
harmonize   →  data/silver/<parcela>/…              grilla 0.1° y 30 m, búfer interno de 30 m, nivel de soporte
simulate    →  data/gold/<parcela>/simulation.json  puntajes 0–100 por corrida (bloque `simulation` del paquete)
package     →  app/public/packages/<id>.<fecha>.json + index.json
```

### Contrato del oro: `data/gold/<parcela>/`

`package.build` arma el paquete con estos archivos (cada uno cumple su parte de `parcel-package.schema.json`):

| Archivo | Obligatorio | Contenido |
|---|---|---|
| `values.json` | sí | Los seis `ContractValue`: `rain`, `bare`, `heat`, `soil`, `moisture`, `slope`. Una fuente que falló va con `value: null` y su razón en `provenance`. |
| `rain_this_season.json` | sí | `{observed: [...], projected: [{y, lo, hi}, ...]}` |
| `green_cover.json` | sí | `{years: {"2013": "CBBBBCNCCCCC", ...}}` (C verde · B sin plantas verdes · N sin dato) |
| `seasons.json` | sí | `[{year, deficit: {p10,p50,p90}, heat_days}, ...]` |
| `thresholds.json` | sí | `{deficit_mm, heat_c}` |
| `meta.json` | sí | `{"clean_pixels": n}` (cuadros de 30 m limpios, sin la orilla) |
| `normals.json` | no | Lo normal en la zona (p10–p90). |
| `map_30m.json` | no | Mapa de 30 m en metros locales. Solo para la parcela de ejemplo o con permiso por escrito. |
| `simulation.json` | no, hasta que exista el simulador | Bloque `simulation` (ver `simulate/run.py`). |

Del `parcels/<id>.yaml` salen `illustrative`, `region_key`, las restricciones y, si hay polígono, `area_ha` y `reference_point` (redondeado a 2 decimales). **El polígono no entra al paquete.**

## Cómo se corre

```bash
cd pipeline
pip install -r requirements.txt
pytest                                           # pruebas (esquema, simulador, armador)

python -m package.validate                       # valida lo publicado en app/public/packages/
python -m package.build --parcel yuc-demo-001    # arma, valida y publica (necesita el oro)
```

`package.build` no escribe nada si el paquete no pasa la validación. El nombre del archivo lleva parcela y fecha (`<id>.<fecha>.json`; el mismo día con otro contenido, `.r2`, `.r3`…) y el paquete anterior se quita para no dejar archivos huérfanos.

## Honestidad

- **No hay oro real todavía**, así que `package.build` hoy solo corre en las pruebas, con partes sacadas del paquete de ejemplo.
- Las pruebas de Python corren con `python -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -m pytest` (43 pruebas, 14 de noviembre de 2026). Las mismas comprobaciones del esquema corren en Node (`cd ../app && npm run check:schema`).
- `requirements.txt` fija solo las dependencias directas. Falta generarlo con sumas de verificación (`pip-compile --generate-hashes`).
- Ninguna parte genera puntajes de mentira: sin simulador, el paquete no lleva `simulation`.
