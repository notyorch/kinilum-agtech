# EDA: qué dicen los datos de la parcela de Guasave

Corrida del 15 de noviembre de 2026 con `python -m ingest.run --parcel sin-demo-001 --lon -108.45673 --lat 25.50826`. El punto es un **ejemplo sorteado cerca de Guasave, Sinaloa** (semilla 20261115, a 6.6 km del centro de la ciudad) y la parcela cuadrada de 200 m es un **supuesto**: nada de esto describe todavía una parcela real. Periodo 2016–2025 (SMAP, solo el último año).

## Estado de las fuentes

| Estado | Fuentes |
|---|---|
| ok | POWER, Open-Meteo (ERA5, solo contraste), **IMERG**, **NASADEM**, **SMAP L4**, SoilGrids, HLS (escenas y píxeles), Sentinel-2 (escenas y respaldo) |
| por integrar | MODIS, ECOSTRESS, GRACE, ERA5-Land |

Los seis valores del contrato salen de datos o de lo que declara el técnico, y `values.json` queda completo. MODIS, ECOSTRESS y GRACE **no se han leído nunca**: no se declaran como fuente.

## Los seis valores

| Valor | Resultado (mediana, rango p10–p90) | Nota |
|---|---|---|
| `bare` (días sin plantas verdes) | 199 días, **al menos** (174–245), unos 6 meses y medio | HLS a 30 m, 597 escenas despejadas de 769 leídas. Un mínimo: los meses con nubes no cuentan. |
| `rain` (lluvia de mayo a octubre) | 446 mm (273–631) | IMERG, años 2016–2024; el punto está a 0.008° del borde de su celda y la vecina da 1.3 % de diferencia. |
| `heat` (máximo de mayo) | 35.5 °C (34.1–37.4) | POWER, región. |
| `moisture` (humedad de la zona de raíz) | 0.229 m³/m³ (0.211–0.306) | SMAP, celda de 9 km a 2.6 km del punto: contexto de zona. |
| `slope` (pendiente) | 3.3 % (1.0–5.7) | NASADEM, 16 píxeles limpios de ~31 m (HLS deja 9). |
| `soil` (profundidad de raíz) | **sin dato** | El suelo se declaró «aluvial», que no tiene rango definido: la mide el técnico en campo. |

SoilGrids sí trae valores en este punto (arcilla de 0 a 5 cm: 36 %, rango 4–64 %, contexto que el paquete no usa), a diferencia del punto de ejemplo anterior.

## Lo que se ve en los datos

- **Un ciclo de invierno con riego.** El NDVI baja a 0.17–0.19 de octubre a diciembre, sube de enero a un máximo de 0.85 en marzo y cae en junio. De enero a mayo el verde se repite todos los años (cultivo de invierno) y de junio a diciembre queda sin plantas verdes casi siempre; 2025 es la excepción, con verde hasta septiembre. Es coherente con una siembra de maíz en la época óptima que da el INIFAP (25 de octubre a 30 de noviembre); el riego y esa siembra que declara la parcela de ejemplo **son supuestos**, no se visitó.
- **El agua depende del riego.** La ET0 anual es de unos 1,850 a 1,990 mm y la lluvia, de unos 490 mm: el balance de agua es negativo en 11 de 12 meses (agosto es el único cercano a cero). La falta de agua en la floración del maíz (Kc medio × ET0 − lluvia, del 24 de enero al 16 de marzo) va de 155 a 291 mm según el año y la fuente (de 177 a 279 mm en la mediana); esa agua tiene que ponerla el riego. Para comparar: el INIFAP da para el maíz de ciclo intermedio 446 mm netos de riego en todo el ciclo (875 mm brutos en cinco riegos).
- **No hay días de calor que dañe en la floración de invierno.** Con 35 °C de umbral, la ventana de floración (del 24 de enero al 16 de marzo) da 0 días todos los años. El calor sí importa en mayo (máximo mediano de 35.5 °C), fuera de esa ventana.
- **Las fuentes de lluvia difieren.** POWER da 542 mm al año; IMERG, 492 mm; Open-Meteo, 411 mm. El sesgo de POWER contra IMERG es de 9.5 % y el de Open-Meteo contra IMERG, de −12.6 %. Por eso el rango de falta de agua es la dispersión **entre fuentes**, no una probabilidad.
- **IMERG Final termina el 30 de septiembre de 2025**: 92 días sin dato. «Lluvia de esta temporada» llega solo hasta ahí.
- **La mitad de las escenas viejas de HLS declaran su proyección como «definida por el usuario»** (código 32767, con UTM 12N en una clave aparte). Un lector estricto las descartaba; aquí se interpretan como UTM 12N con elipsoide WGS84.
- **Mosaico:** todas las escenas de HLS del punto son del mosaico `T12RYP`.

## Decisiones que no son del código

| Decisión | Quién | Qué cambia |
|---|---|---|
| Coordenadas, tamaño y cultivo de la parcela real | Equipo con técnico | Todo lo anterior depende del punto sorteado. |
| Riego y siembra en noviembre (la época óptima del maíz según el INIFAP: 25 de octubre a 30 de noviembre) | Técnico local | Cambian la ventana de floración y la falta de agua. `rules/maize.v1.yaml` usa 84 a 106 días a floración (INIFAP, Tabla 15, que no aclara si cuenta desde siembra o emergencia). |
| Umbral de NDVI de 0.35 para «sin plantas verdes» | Técnico local | En este punto el verde de invierno es claro, pero el umbral es una propuesta. |
| Umbral de «temporada difícil» (p75 de la falta de agua: 253 mm) | Equipo con técnico | Es una propuesta; marca qué años se consideran difíciles. |
| Qué viento usar en la ET0 (el de POWER o 2 m/s de FAO-56) | Equipo con técnico | La ET0 cambia hasta 7 %; las conclusiones cualitativas, no. |
| Profundidad de raíz de los cultivos de rotación y calor que daña (frijol, garbanzo, trigo) | Técnico local | Siguen «sin dato»: el INIFAP no los da. Fechas de siembra, ciclo y riegos ya salen de la Agenda Técnica de Sinaloa 2017 y el rendimiento y el precio, del SIAP (`pipeline/rules/sources/`). |

## Cómo repetirlo

```bash
cd pipeline
.venv/bin/python -m ingest.run --parcel sin-demo-001 --lon -108.45673 --lat 25.50826
.venv/bin/python -m package.build --parcel sin-demo-001
```
