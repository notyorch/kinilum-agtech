# rules — catálogo de cultivos versionado

`crops.<versión>.yaml` dice qué cultivos de rotación se comparan con el maíz y con qué reglas. Hoy: `crops.v2.yaml`, con **frijol, garbanzo, sorgo y trigo**. No se simulan más cultivos que estos cuatro.

## El contrato

- **Cabecera:** `rules_version`, `fuente`, `validado_por` y `method`. Mientras un valor sea un supuesto del equipo, `method: assumed`.
- **Por cultivo:** `tipo` (leguminosa o cereal), `estrategia` (E2–E5), `fija_nitrogeno`, `exige_maquinaria`, `requiere_venta`, `ciclo_dias`, los parámetros FAO-56 (`kc_por_etapa`, `profundidad_raiz_m`), `ventana_siembra`, `umbral_calor_c`, `rendimiento_t_ha`, `precio_mxn_t` y `estado_evidencia`.
- **`null` significa «por definir».** Se llena con el técnico y una fuente citada. Si falta un parámetro, el criterio que lo necesita se declara «sin dato»; nunca se rellena con un valor inventado.
- **`estado_evidencia: a_validar`** en todo lo que no tenga fuente. La app lo muestra como «A validar con el técnico».
- **Solo las leguminosas suman nitrógeno:** frijol y garbanzo sí; sorgo y trigo no.

## Datos locales con fuente (`sources/`)

`sources/siap_guasave_oi_riego.yaml` guarda, año por año (2015–2024), la superficie sembrada, el rendimiento y el precio medio rural de maíz, frijol, garbanzo, sorgo y trigo en **Guasave, otoño-invierno y riego**. Salen del Cierre de la producción agrícola del SIAP (consulta por municipio, leída el 15 de noviembre de 2026). El catálogo solo resume esa tabla (mediana y p10–p90; el precio, de 2020 a 2024 y en pesos corrientes) y una prueba comprueba que coincidan.

- Son datos **del municipio**, no de la parcela, y «frijol» agrupa todos los tipos.
- Con rendimiento y precio, el criterio de **ingreso** ya se puede calcular. **Agua y clima siguen sin dato**: faltan el ciclo, las fechas de siembra, la profundidad de raíz y el Kc inicial.

## Variantes del frijol regional (E2)

Cada variante es un perfil completo, con los mismos campos que un cultivo. Hoy solo hay `negro` (por defecto); los tipos de frijol que más se siembran en Guasave se agregan con el técnico. La elige el técnico en `pipeline/parcels/<id>.yaml`, campo `frijol_variante`. El paquete lleva solo la variante elegida (`rotation.E2.variant`), cambiarla cambia el nombre del archivo y la app la nombra en «Evidencia».

Los nombres científicos se revisan con el técnico antes de publicarlos.

## Reglas de restricción

Son filtros, no pesos. Una estrategia que no cumple **no se oculta**: va al final de la lista, con su razón.

| Regla | Qué hace |
|---|---|
| `no_aceptado` | Si el agricultor no acepta el cultivo, la estrategia queda fuera. |
| `sin_venta` | Sin dónde vender: frijol, garbanzo, sorgo y trigo quedan fuera. |
| `sin_maquinaria` | Sin tractor ni maquila: sorgo y trigo quedan fuera. |
| `calor_extremo_suelo_delgado` | Garbanzo y trigo se marcan «poco viable», con la razón visible. |

## Otras reglas: maíz y suelo

- `maize.v1.yaml`: días entre siembra y floración (55 a 75) y el umbral de calor que daña (35 °C). Con ellos se define la ventana de floración (`harmonize/phenology.py`).
- `soil.v1.yaml`: profundidad de raíz por tipo de suelo declarado (aluvial o sin declarar). Ninguno tiene hoy un rango con fuente, así que `root_depth` queda **sin dato** hasta que el técnico la mida (`root_depth_cm`). No sale de SoilGrids.

Ambos son supuestos del equipo, sin fuente, y dicen `estado_evidencia: a_validar`: el técnico local los corrige.

## Quién lo lee

- **La app** lleva un espejo en `app/src/data/crops.ts` y `app/src/data/restrictions.ts`. La prueba `app/tests/data.test.mjs` falla si el espejo y este catálogo dejan de coincidir.
- **El pipeline** lo lee con `pipeline/simulate/crops.py`: el perfil de cada cultivo y variante, quién suma nitrógeno y qué criterios quedan sin dato. El armador (`package/build.py`) escribe el bloque `rotation` del paquete con la variante elegida. `simulate/run.py` sigue pendiente; cuando exista, escribe `rules_version` en el bloque `simulation`.

Las reglas y los modelos físicos (FAO-56, umbrales) calculan; un LLM solo puede redactar desde la traza.
