# harmonize — de bronce a plata y oro

Pone los datos en las mismas grillas, le da a cada valor su **nivel de soporte** y construye los valores del contrato.

- Grillas de **0.1°** (zona y región) y de **30 m** (parcela).
- **Búfer interno de 30 m**: un píxel de 30 m mezcla cultivo, borde y camino; se descarta el borde. De aquí sale `clean_pixels`. Con una parcela de 200 m quedan entre 9 y 16 píxeles de 30 m según cómo caiga la cuadrícula.
- **`support_level`** de cada valor: `parcel` (HLS, NASADEM, lo declarado), `surroundings` (MODIS a 250 m), `zone` (IMERG, SMAP) y `region` (POWER). Los datos de zona y región son contexto («en su zona»), nunca color dentro del polígono.
- **Profundidad de raíz para FAO-56:** sale de lo declarado por el técnico, **no** de SoilGrids. Una medición de campo (`root_depth_cm` en el yaml) reemplaza el rango.
- El índice de vegetación detecta «sin plantas verdes», no «suelo desnudo».
- **Memoria honesta:** HLS a 30 m existe desde 2013; MODIS a 250 m, desde 2000. Se dice «décadas de clima y años de observación satelital», no «20 años de su parcela».
- Una fuente sin dato **no se rellena**: el valor sale con `value: null`, y el criterio que dependía de ella se calcula sin ella.

Cada valor que sale de aquí cumple `shared/schema/contract-value.schema.json`.

## Cómo se define cada valor (`values.py`)

Todos usan **mediana, p10 y p90 entre años (o días)**, y exigen un mínimo: con menos, el valor sale **sin dato**, nunca recortado.

| Valor | Fuente | Criterio | Mínimo |
|---|---|---|---|
| `rain` → `rain_season` | IMERG (zona) | Suma de **mayo a octubre** de cada año; mediana y rango entre años. | 3 años con los 184 días y sin faltantes |
| `heat` → `tmax_may` | POWER (región) | **Máximo de mayo** de cada año (el día más caluroso), de `T2M_MAX`; mediana y rango entre años. Se eligió el máximo y no el promedio de las máximas porque el calor que daña es el extremo y porque así lo definía el paquete de ejemplo. | 3 años con mayo completo |
| `moisture` → `soil_moisture_rootzone` | SMAP L4 (zona) | Humedad de la zona de raíz (0–100 cm), un granulo por día (16:30 UTC); mediana y rango entre días de los últimos 365. | 80 % de los días |
| `slope` | NASADEM (parcela) | Pendiente de Horn de los píxeles completos dentro de la parcela tras descartar 30 m de borde; mediana y rango entre píxeles. | 1 píxel limpio con dato |
| `soil` → `root_depth` | Lo declara el técnico | Mitad del rango del tipo de suelo (`rules/soil.v1.yaml`), con el rango como p10–p90; una medición de campo lo reemplaza. | — |
| `bare` | HLS | Pendiente de construir: necesita los píxeles de HLS. | — |

## Ventana de floración (`phenology.py`)

Es el calendario del maíz de temporal, y es un **supuesto del equipo, a validar con el técnico** (`rules/maize.v1.yaml`, sin fuente): la parcela se siembra a lo largo del mes declarado (`sowing`) y el maíz florece **55 a 75 días después**. La ventana empieza 55 días después del primer día del mes y termina 75 días después del último: con siembra en junio, del 26 de julio al 13 de septiembre. Dentro de ella se cuentan los días con temperatura máxima ≥ 35 °C (`heat_days_in_window`), solo en años con la ventana completa. Si el técnico da otros días o otro umbral, se cambia el archivo de reglas y nada más.
