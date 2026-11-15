# rules — catálogo de cultivos versionado

`crops.<versión>.yaml` dice qué cultivos de rotación se comparan con el maíz y con qué reglas. Hoy: `crops.v1.yaml`, con **frijol, garbanzo, sorgo y trigo**. No se simulan más cultivos que estos cuatro.

## El contrato

- **Cabecera:** `rules_version`, `fuente`, `validado_por` y `method`. Mientras un valor sea un supuesto del equipo, `method: assumed`.
- **Por cultivo:** `tipo` (leguminosa o cereal), `estrategia` (E2–E5), `fija_nitrogeno`, `exige_maquinaria`, `requiere_venta`, `ciclo_dias`, los parámetros FAO-56 (`kc_por_etapa`, `profundidad_raiz_m`), `ventana_siembra`, `umbral_calor_c`, `rendimiento_t_ha`, `precio_mxn_t` y `estado_evidencia`.
- **`null` significa «por definir».** Se llena con el técnico y una fuente citada. Si falta un parámetro, el criterio que lo necesita se declara «sin dato»; nunca se rellena con un valor inventado.
- **`estado_evidencia: a_validar`** en todo lo que no tenga fuente. La app lo muestra como «A validar con el técnico».
- **Solo las leguminosas suman nitrógeno:** frijol y garbanzo sí; sorgo y trigo no.

## Variantes del frijol regional (E2)

Cada variante es un perfil completo, con los mismos campos que un cultivo: `xpelon` (por defecto en Yucatán), `ib` y `negro`. La elige el técnico en `pipeline/parcels/<id>.yaml`, campo `frijol_variante`. El paquete lleva solo la variante elegida (`rotation.E2.variant`), cambiarla cambia el nombre del archivo y la app la nombra en «Evidencia».

La tolerancia del xpelón al calor y a la sequía es una hipótesis sin fuente: queda `a_validar` y no se usa para ordenar con peso fuerte. Los nombres científicos se revisan con el técnico antes de publicarlos.

## Reglas de restricción

Son filtros, no pesos. Una estrategia que no cumple **no se oculta**: va al final de la lista, con su razón.

| Regla | Qué hace |
|---|---|
| `no_aceptado` | Si el agricultor no acepta el cultivo, la estrategia queda fuera. |
| `sin_venta` | Sin dónde vender: frijol, garbanzo, sorgo y trigo quedan fuera. |
| `sin_maquinaria` | Sin tractor ni maquila: sorgo y trigo quedan fuera. |
| `calor_extremo_suelo_delgado` | Garbanzo y trigo se marcan «poco viable», con la razón visible. |

## Quién lo lee

- **La app** lleva un espejo en `app/src/data/crops.ts` y `app/src/data/restrictions.ts`. La prueba `app/tests/data.test.mjs` falla si el espejo y este catálogo dejan de coincidir.
- **El pipeline** lo lee con `pipeline/simulate/crops.py`: el perfil de cada cultivo y variante, quién suma nitrógeno y qué criterios quedan sin dato. El armador (`package/build.py`) escribe el bloque `rotation` del paquete con la variante elegida. `simulate/run.py` sigue pendiente; cuando exista, escribe `rules_version` en el bloque `simulation`.

Las reglas y los modelos físicos (FAO-56, umbrales) calculan; un LLM solo puede redactar desde la traza.
