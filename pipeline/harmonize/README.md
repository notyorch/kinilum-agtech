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
| `bare` → `days_without_green_cover` | HLS (parcela); Sentinel-2 de respaldo | NDVI de los píxeles completos dentro de la parcela tras descartar 30 m de borde, solo con Fmask limpio (SCL en Sentinel-2); la mediana por mes se compara con **0.35** (propuesta, a calibrar). Días de los meses por debajo del umbral, por año; mediana y rango entre años. Los meses sin escena despejada **no cuentan** como «sin plantas verdes», así que es un **mínimo**. No se calcula BSI: afirmaría «suelo desnudo». | 9 meses con dato por año y 3 años |

## Partes del oro que no son un valor (`season.py`)

Salen de las mismas series; si falta una fuente, la parte no se escribe y `ingest.run` dice por qué.

| Archivo | Cómo se arma |
|---|---|
| `seasons.json` | Por **año de floración** (la siembra de noviembre florece del 24 de enero al 16 de marzo del año siguiente): falta de agua en la ventana de floración (`Kc` de la etapa media del maíz × ET0 − lluvia, en mm; con riego, cuánta agua tiene que poner el riego) y días de calor que daña. El rango p10/p50/p90 es el mínimo, la mediana y el máximo **entre las cuatro combinaciones de fuente** (lluvia de IMERG u Open-Meteo; ET0 de Open-Meteo o de Penman–Monteith con POWER y viento de 2 m/s): dispersión entre fuentes, no probabilidad. |
| `rain_this_season.json` | Lluvia acumulada por mes del último año con datos (IMERG) y, para los meses que faltan, la banda p10, mediana y p90 de lo que llovió en esos meses en los demás años (empírico, no un pronóstico). |
| `normals.json` | Lluvia de mayo a octubre y máximo de mayo, p10–p90 entre los años con datos, con su periodo y fuente. |
| `thresholds.json` | Propuesta, a validar con el técnico: temporada difícil si su falta de agua pasa del **p75** de las temporadas; calor de `maize.v1.yaml` (35 °C). |
| `meta.json` | Cuadros de 30 m limpios de la parcela (los que leyó HLS). |

El coeficiente `Kc` medio del maíz sale de `rules/crops.v2.yaml` (`maiz_base`, FAO-56 Tabla 12). El Kc inicial no se pudo leer de la fuente y no se usa: no se calcula ninguna etapa inicial.

## Ventana de floración (`phenology.py`)

Es el calendario del maíz de riego en otoño-invierno (`rules/maize.v1.yaml`): la parcela se siembra a lo largo del mes declarado (`sowing`) y el maíz florece **84 a 106 días después**, la floración femenina de los híbridos que evaluó el CEVAF en 2015 y 2016 (INIFAP, Agenda Técnica de Sinaloa 2017, Tabla 15; la tabla no aclara si cuenta desde siembra o emergencia). La ventana empieza 84 días después del primer día del mes y termina 106 días después del último: con siembra en noviembre, del 24 de enero al 16 de marzo del año siguiente. El umbral de calor de 35 °C sigue siendo un **supuesto del equipo, a validar con el técnico**. Dentro de ella se cuentan los días con temperatura máxima ≥ 35 °C (`heat_days_in_window`), solo en años con la ventana completa. Si el técnico da otros días o otro umbral, se cambia el archivo de reglas y nada más.

## Del dato al puntaje (`simulate/`)

El simulador no vive aquí, pero usa lo de arriba: la lluvia de IMERG, la temperatura de POWER y el catálogo. **Agua** por estrategia = promedio de la necesidad de riego de un ciclo de maíz y uno del cultivo de rotación (ETc de FAO-56 − lluvia del ciclo; las etapas de Kc se escalan al ciclo del INIFAP; el maíz usa grados día para su ciclo). **Ingreso** = rendimiento × precio medio rural del SIAP del mismo año (2020–2024), bruto y por hectárea. El puntaje de agua es 100 cuando no pide riego y 0 cuando pide el percentil 95 del maíz entre todas las celdas; el de ingreso, el ingreso del percentil 95 del maíz. Con el maíz de ciclo intermedio, el simulador da unos 430 mm de riego neto en el escenario normal; el INIFAP da 446 mm (Tabla 21).
