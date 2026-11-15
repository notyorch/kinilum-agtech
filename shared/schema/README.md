# shared/schema — el contrato de datos

Es la interfaz entre el pipeline (Python) y la app (TypeScript): si todos escriben contra el mismo esquema, nadie necesita leer el código de los demás. El pipeline valida **antes de escribir**; la app y el CI validan **al cargar y al compilar**.

> **Cambiar algo aquí requiere la aprobación de Jorge** (ARQUITECTURA-DEV §12). Un cambio incompatible sube `package_format`.

| Archivo | Qué describe | Quién lo escribe | Quién lo lee |
|---|---|---|---|
| `contract-value.schema.json` | Un valor del contrato: `{variable, value, p10, p90, unit, source, native_resolution, derived_resolution, support_level, timestamp, method, quality, assumptions[], provenance[]}`. El motor nunca recibe un número suelto. | pipeline | app, motor |
| `parcel-package.schema.json` | El paquete de una parcela (`app/public/packages/<id>.<fecha>.json`), con valores, cubierta, temporadas, restricciones, mapa de 30 m y, cuando exista el simulador, los puntajes por corrida. | `pipeline/package/build.py` | app |
| `package-index.schema.json` | `app/public/packages/index.json`: a qué archivo apunta cada parcela. | `pipeline/package/build.py` | app |
| `parcel-config.schema.json` | `pipeline/parcels/<id>.yaml`: lo que declara el técnico. Lleva el polígono exacto: **nunca se publica**. | técnico | pipeline |

JSON Schema **draft-07** (lo entienden por igual `jsonschema` en Python, `ajv` en Node y `json-schema-to-typescript`).

## Reglas que el esquema hace cumplir

- **`kinilum-package/2`** (14 de noviembre de 2026): seis estrategias (E0–E5); `restrictions` cambia `crops` por `cultivos_aceptados` y usa los cultivos del catálogo (frijol, garbanzo, sorgo, trigo), y suma `soil` y `extreme_heat`; bloque nuevo `rotation` (cultivo por estrategia y, en E2, `variant` y `variant_chosen_by`); `simulation.no_data`. En la configuración de la parcela, `bean_variety` pasa a llamarse `frijol_variante`.
- Un valor sin `support_level`, `p10` o `p90` no pasa. `value: null` (sin dato) exige `p10` y `p90` nulos: una fuente que falla se declara, no se rellena.
- `method`: `measured | interpolated | modeled | assumed`. `support_level`: `parcel | surroundings | zone | region`.
- El paquete no admite campos que no estén en el esquema (`additionalProperties: false`): un polígono, un nombre o una coordenada no caben.
- `simulation`: 49 celdas (grilla de «¿Qué pasa si…?»), puntajes enteros 0–100 como bytes en base64, disposición `[estrategia][criterio][corrida]`. Sin percentiles por criterio: impedirían contar veces en primer lugar.

## Lo que el esquema JSON no dice (comprobaciones «semánticas»)

Viven en **dos sitios que deben decir lo mismo**: `pipeline/package/validate.py` y `app/scripts/check-schema.mjs`.

- `p10 ≤ value ≤ p90`, y `lo ≤ y ≤ hi`, y `p10 ≤ p50 ≤ p90` en las temporadas.
- `reference_point` con a lo más 2 decimales (≈ 1 km); ningún campo `polygon`, `geometry`, `lat`, `lon`…
- `clean_pixels` = cuadros `c` de la máscara; las capas del mapa miden lo mismo que la máscara.
- `simulation`: 49 celdas distintas; las 6 con nombre (`normal`, `dry`, `veryDry`, `wet`, `hot`, `dryHot`) en su lugar y con 500 corridas, las demás con 100; `scores` mide `6 × 5 × runs` bytes (E0–E5) y ninguno pasa de 100, salvo el 255 de un criterio declarado en `no_data`, que vale 255 en todas sus corridas.
- `rotation`: cada estrategia trae su cultivo (E2 frijol, E3 sorgo, E4 garbanzo, E5 trigo) y `rules_version` coincide con la de `simulation`.
- Tamaño: menos de 500 KB.

## Tipos de TypeScript

Se **generan** desde estos archivos; no se editan a mano:

```bash
cd app
npm run gen:schema        # escribe src/data/schema.gen.ts
npm run build             # falla si schema.gen.ts no coincide con el esquema
```

## Cómo probarlo

```bash
cd app && npm run check:schema        # índice y paquetes publicados + autoprueba (acepta lo bueno, rechaza lo malo)
cd pipeline && pytest                  # lo mismo desde Python, más el armador de paquetes
```

## Estado (14 de noviembre de 2026)

- El paquete de ejemplo (`sin-demo-001.2026-11-14.json`, formato `kinilum-package/2`) cumple el esquema, **sin** el bloque `simulation`: los resultados por objetivo y por escenario siguen siendo ejemplo escrito a mano en `app/src/data/scenarios.ts`.
- Un bloque `simulation` sintético (bytes pseudoaleatorios, solo para probar la forma) con las seis estrategias mide unos 293 KB: pasa el objetivo de ≈ 260 KB, pero cabe en el límite de 500 KB.
- Pendiente: que el simulador y el motor acuerden sobre este bloque; la validación completa en la app (hoy solo rechaza un `package_format` que no conoce).
