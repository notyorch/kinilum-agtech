# EDA: qué dicen los datos (primera corrida real)

Corrida del 15 de noviembre de 2026 con `python -m ingest.run --lon -89.42 --lat 20.30`. El punto es un **ejemplo cerca de Oxkutzcab** y la parcela cuadrada de 200 m es un **supuesto**: nada de esto describe todavía la parcela real. Periodo 2016–2025. Se corrió sin token de Earthdata, así que las fuentes que lo piden quedaron «por integrar».

## Estado de las fuentes

| Estado | Fuentes |
|---|---|
| ok | POWER, Open-Meteo (ERA5), HLS (escenas), Sentinel-2 (escenas) |
| sin dato | SoilGrids |
| por integrar (falta `EARTHDATA_TOKEN`) | IMERG, NASADEM, MODIS, SMAP, ECOSTRESS, GRACE |
| por integrar (falta `CDS_API_KEY`) | ERA5-Land |

Decisión de entrega del plan de degradación: **DETENER**. NASADEM es del núcleo y no tiene respaldo.

## Lo que se encontró

1. **SoilGrids no tiene valores en el punto.** Respondió 200 con las 30 capas (6 propiedades × 5 profundidades) nulas, y el notebook de exploración lo daba por «ok». Ahora es «sin dato». Coincide con la regla del PRD: la profundidad de raíz sale del técnico, no de SoilGrids.
2. **El viento de POWER es casi cero.** La mediana de `WS2M` es 0.00 m/s (a 10 m, 0.94 m/s). Con ese viento la ET0 de FAO-56 queda **22.9 % por debajo** de la de Open-Meteo. Con el valor por defecto de FAO-56 (2 m/s) queda a **−1.0 %** y la correlación diaria sube de 0.82 a 0.92. Los meses con balance de agua negativo (enero a mayo, julio, noviembre y diciembre) son los mismos con ambos vientos; cambia cuánto: en marzo, −103 mm contra −163 mm.
3. **POWER y Open-Meteo no coinciden en cuánta lluvia cae.** POWER da 1,119 mm al año (mediana entre años) y Open-Meteo, 779 mm: POWER llueve 42.4 % más. Coinciden en cuándo (correlación mensual 0.92, acuerdo día lluvioso o seco 81 %). El notebook reportó −29.8 % porque midió al revés, (Open-Meteo − POWER) / POWER: el mismo dato, pero se lee como «POWER llueve menos». Ninguna de las dos es la verdad; IMERG y un técnico local deben arbitrar.
4. **HLS tiene 1,803 escenas únicas y 424 limpias** (≤ 30 % de nubes), no las 3,590 y 846 del notebook: contaba cada escena dos veces por las colecciones de índices de vegetación. Nubes: mediana 56 %, p90 87 %.
5. **En lluvias casi no hay escenas limpias.** Escenas limpias por mes del año en diez años: de junio a septiembre, 11 a 16; en marzo y abril, 73 y 80. 28 de 120 meses no tienen ninguna limpia, todos con escenas pero nubladas. La señal de «sin plantas verdes» (noviembre a marzo) está bien cubierta; la de la temporada de lluvias, floja.
6. **Sentinel-2 como respaldo solo cubre desde enero de 2017** en este punto: 2016 no tiene escenas.
7. **Calor de mayo (POWER, región):** máximas diarias medias de 37.1 °C (p10 35.4, p90 39.2). El día más caluroso del periodo pasó de 43 °C.
8. **Racha seca más larga por año:** mediana de 26 días (p10 18, p90 29).

## Errores del notebook de exploración que se corrigieron aquí

- La fecha de Sentinel-2 fallaba por mezclar formatos con y sin fracción de segundo.
- El informe final (E8) terminaba en error; la causa probable es que intentaba convertir en número el valor nulo de SoilGrids.
- CMR-STAC devuelve 502 con páginas de más de ~1 MB; el notebook se salvaba por suerte según el tamaño del periodo.
- El listado de colecciones de CMR-STAC viene paginado y solo se leía la primera página.

## Decisiones que no son del código

| Decisión | Quién | Qué cambia |
|---|---|---|
| Qué viento usar en el balance de agua: el de POWER, 2 m/s de FAO-56 u otra fuente | Equipo con técnico | La ET0 cambia hasta 29 %; las conclusiones cualitativas, no. |
| Si Open-Meteo o POWER sustituye a IMERG mientras no llegue el token | Equipo | Hoy la lluvia de zona queda sin dato. |
| Pedir HLS desde 2013 | Equipo | La cuadrícula de cubierta del paquete va de 2013 a 2025; esta corrida pidió desde 2016. |
| Definir «temperatura máxima de mayo»: media de máximas diarias o la más alta | Equipo | Cambia el número del paquete (37.1 °C contra más de 43 °C). |
| Token de Earthdata | Quien tenga la cuenta | **Ya hay token y el acceso a IMERG, NASADEM, MODIS y HLS está confirmado** (`python -m ingest.access`, 15 de noviembre). Falta integrar la lectura de valores; el EDA de arriba se corrió antes, sin token. |
| Coordenadas y tamaño de la parcela real | Equipo con técnico | Todo lo anterior depende del punto. |

## Cómo repetirlo

```bash
cd pipeline
.venv/bin/python -m ingest.run --lon -89.42 --lat 20.30
```

Deja el informe en `pipeline/data/eda/yuc-demo-001/` (`eda_report.json` y `eda_report.md`). Los umbrales del informe (nubes máximas 30 %, día lluvioso ≥ 1 mm, sesgos de 25 % y 20 %) son una **propuesta** que se calibra con un técnico local.
