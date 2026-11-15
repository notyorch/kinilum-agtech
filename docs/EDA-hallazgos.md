# EDA: qué dicen los datos

Corridas del 15 de noviembre de 2026 con `python -m ingest.run --lon -89.42 --lat 20.30`. El punto es un **ejemplo cerca de Oxkutzcab** y la parcela cuadrada de 200 m es un **supuesto**: nada de esto describe todavía la parcela real. Periodo 2016–2025 (SMAP, solo 2025).

## Estado de las fuentes

| Estado | Fuentes |
|---|---|
| ok | POWER, Open-Meteo (ERA5), **IMERG**, **NASADEM**, **SMAP L4**, SoilGrids (celda vecina), HLS (escenas y píxeles), Sentinel-2 (escenas y respaldo) |
| por integrar | MODIS, ECOSTRESS, GRACE, ERA5-Land |

Los seis valores del contrato ya salen de datos o de lo que declara el técnico (`rain`, `slope`, `heat`, `moisture`, `soil` y `bare`), y `values.json` queda completo.

## Plantas verdes (HLS)

Se leyeron los píxeles de 659 escenas de HLS del mosaico del punto (con 70 % de nubes o menos en el mosaico entero). En **237** la parcela quedó despejada y en 422 había nubes sobre ella. Para 16 meses sin escena limpia de HLS se usó Sentinel-2 como respaldo. En total, 253 observaciones despejadas.

- **El punto de ejemplo está verde todo el año.** El NDVI nunca bajó de 0.36 (mínimo en abril y mayo, mediana 0.52 a 0.54; máximo en diciembre, 0.71). Con el umbral de 0.35 los días sin plantas verdes salen **0 (rango 0 a 0)**, medidos en 8 años con al menos 9 meses con dato. Es lo que hay en esas coordenadas, no un fallo: el patrón estacional es lógico (más bajo en secas, más alto en lluvias). Pero **contradice el «unos 3 meses y medio» escrito a mano en la app**, que sigue siendo un dato de ejemplo.
- Un punto cercano a Oxkutzcab puede caer sobre monte o huerta; una milpa con rastrojo seco se vería distinta. Antes de dar este valor por la parcela real hay que fijar sus coordenadas con el técnico.
- El umbral de 0.35 es una propuesta: en la época seca el mínimo (0.36) está pegado a él, así que moverlo a 0.40 ya cambiaría el resultado.
- En 2016 y 2022 faltan demasiados meses (8 o menos con dato) y no cuentan. Los meses sin escena despejada (sobre todo en lluvias) no se cuentan como «sin plantas verdes»: el valor es un mínimo.
- Las escenas de HLS anteriores a cierta fecha traen la proyección como «definida por el usuario» (código 32767, con UTM 16N en una clave aparte), cerca de la mitad de las escenas. Un lector estricto las descartaba; aquí se interpretan como UTM 16N con elipsoide WGS84 y se verificó contra rasterio en una escena nueva y una vieja.

## Lluvia: IMERG dirime

| Par | Lluvia anual (mediana) | Sesgo | Correlación mensual |
|---|---|---|---|
| POWER contra IMERG | 1,125 y 1,151 mm | −1.5 % | 0.955 |
| Open-Meteo contra IMERG | 737 y 1,151 mm | −30.8 % | 0.887 |
| POWER contra Open-Meteo | 1,119 y 779 mm | +42.4 % | 0.922 |

**IMERG y POWER coinciden; Open-Meteo (ERA5) se queda corto unos 30 %.** No hay una estación local que lo confirme, pero con dos fuentes independientes de acuerdo, la duda de la primera corrida («¿cuál es la verdad?») se resuelve a favor de IMERG: ya no hace falta decidir si Open-Meteo lo sustituye. (El notebook de exploración reportó −29.8 % porque medía al revés, (Open-Meteo − POWER) / POWER; ahora el signo está explícito.)

- **IMERG Final llega hasta el 30 de septiembre de 2025**: octubre a diciembre de 2025 no existen todavía (92 días). Por eso solo hay **9 años completos de mayo a octubre (2016–2024)** y `rain_season` sale de esos.
- **El punto cae exactamente en el borde entre dos celdas de IMERG** (20.30° N). La celda vecina da 1,157 mm al año contra 1,151 mm (0.4 %), correlación mensual 0.996 y 93 % de acuerdo día lluvioso o seco: el borde pesa poco en totales, algo más en días sueltos.
- **Lluvia de mayo a octubre (`rain_season`):** mediana de 948 mm, con p10 de 833 y p90 de 1,191 entre los 9 años.

## Humedad del suelo (SMAP L4)

Humedad de la zona de raíz (0–100 cm) de la celda de 9 km más cercana (a 3.1 km del punto), un granulo por día, 2025 completo (365 de 365 días): mediana de **0.211 m³/m³** (p10 0.180, p90 0.244). Sigue a la lluvia con retraso: mínimo en mayo (0.176) y máximo en octubre (0.261). Como comprobación independiente, el 3 de junio de 2025 la humedad **superficial** sube de 0.10 a 0.185 m³/m³ el mismo día en que IMERG ve 20 mm. Es contexto de zona, no la humedad de la parcela.

## Calor

- **Máxima de mayo (`tmax_may`, POWER):** el día más caluroso de cada mayo; mediana de **40.1 °C** (p10 38.9, p90 41.4) entre 2016 y 2025; por año va de 37.8 a 43.2 °C. El promedio de las máximas diarias de mayo es 37.1 °C.
- **Días de calor en la floración:** con siembra en junio, la ventana (supuesto: 55 a 75 días después de sembrar) va del 26 de julio al 13 de septiembre. Los días con máxima ≥ 35 °C en esa ventana van de **0 a 19 por año** (2019: 19, 2025: 11, siete años con 0 a 2).

## Terreno (NASADEM)

- **Elevación 29 m** en el punto (28 a 33 m en la parcela). Open-Meteo reporta 29.0 m y POWER 29.2 m: coinciden. El notebook suponía 40 m.
- **Pendiente:** mediana de 6.1 % (p10 1.7, p90 7.5) con **9 píxeles completos** de ~31 m, no los 16 de la fórmula. En terreno casi plano un escalón de un metro entre píxeles ya son ~3 %: la pendiente tiene un piso de ruido y conviene leerla por clases.

## Otros hallazgos

1. **SoilGrids no tiene valores en el punto.** Respondió 200 con las 30 capas (6 propiedades × 5 profundidades) nulas, y el notebook de exploración lo daba por «ok». Ahora se prueban celdas vecinas a 250, 500 y 1,000 m: la primera con valores fue la de **250 m al suroeste**, y la arcilla sale marcada como interpolada. Si no hubiera ninguna, queda «sin dato». La profundidad de raíz (`soil`) no depende de él: la declara el técnico.
2. **El viento de POWER es casi cero** (mediana 0.00 m/s a 2 m; 0.94 m/s a 10 m). Con él, la ET0 de FAO-56 queda 23.0 % por debajo de la de Open-Meteo; con el valor por defecto de FAO-56 (2 m/s), a −1.0 % y la correlación diaria sube de 0.82 a 0.92. Los meses de balance de agua negativo (enero a mayo, julio, noviembre y diciembre) son los mismos con ambos vientos; cambia cuánto.
3. **HLS tiene 1,803 escenas únicas y 424 limpias** (≤ 30 % de nubes), no las 3,590 y 846 del notebook, que contaba cada escena dos veces por las colecciones de índices de vegetación. Nubes: mediana 56 %, p90 87 %.
4. **En lluvias casi no hay escenas limpias:** de junio a septiembre, 11 a 16 en diez años; en marzo y abril, 73 y 80. 28 de 120 meses no tienen ninguna limpia, todos con escenas pero nubladas. La señal de «sin plantas verdes» (noviembre a marzo) está bien cubierta; la de lluvias, floja.
5. **Sentinel-2 como respaldo solo cubre desde enero de 2017** en este punto.
6. **Racha seca más larga por año:** mediana de 26 días (p10 18, p90 29).
7. **CMR-STAC devuelve 502 con páginas de más de ~1 MB** (cada escena pesa ~12 KB); se piden 50 por página.

## Errores del notebook de exploración que se corrigieron aquí

- La fecha de Sentinel-2 fallaba por mezclar formatos con y sin fracción de segundo.
- El informe final (E8) terminaba en `TypeError: float() argument must be a string or a real number, not 'NoneType'`: convertía en número el valor nulo de SoilGrids. Reproducido con la respuesta nula en caché y corregido: un valor que falta queda como `None` y SoilGrids busca la celda vecina. El notebook corregido está en `pipeline/notebooks/kinilum_eda_00.ipynb`.
- CMR-STAC devuelve 502 con páginas de más de ~1 MB y el listado de colecciones viene paginado; el notebook leía solo la primera página.
- SoilGrids se daba por «ok» con todos los valores nulos.

## Decisiones que no son del código

| Decisión | Quién | Qué cambia |
|---|---|---|
| Qué viento usar en el balance de agua: el de POWER, 2 m/s de FAO-56 u otra fuente | Equipo con técnico | La ET0 cambia hasta 29 %; las conclusiones cualitativas, no. |
| Pedir HLS desde 2013 | Equipo | La cuadrícula de cubierta va de 2013 a 2025; esta corrida pidió desde 2016. |
| «Temperatura máxima de mayo»: se tomó el **máximo del mes** (el día más caluroso), como el paquete de ejemplo | Equipo | Con el promedio de las máximas sería 37.1 °C en vez de 40.1 °C. |
| Días de siembra a floración (55 a 75) y umbral de calor (35 °C) | Técnico local | Cambian la ventana y los días de calor; no los datos. Están en `rules/maize.v1.yaml`, «a validar». |
| Coordenadas y tamaño de la parcela real | Equipo con técnico | Todo lo anterior depende del punto. |

## Cómo repetirlo

```bash
cd pipeline
.venv/bin/python -m ingest.run --lon -89.42 --lat 20.30
```

Deja el informe en `pipeline/data/eda/yuc-demo-001/` y los valores del contrato en `pipeline/data/gold/yuc-demo-001/values.partial.json`. La primera corrida tarda unos 20 minutos por las ~3,650 peticiones de IMERG; las siguientes salen de la caché. Los umbrales del informe (nubes máximas 30 %, día lluvioso ≥ 1 mm, sesgos de 25 % y 20 %) son una **propuesta** que se calibra con un técnico local.
