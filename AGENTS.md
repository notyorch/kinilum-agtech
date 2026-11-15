# AGENTS.md — kinilum

Guía para cualquier agente de IA (Claude, Codex, etc.) que trabaje en este repositorio: qué es el proyecto, para quién es, cómo está construido, qué reglas no se rompen y cómo probarlo. Está escrita en español porque el equipo, el producto y los textos de la interfaz lo están.

Este archivo **resume y complementa** a los documentos fuente. Si algo aquí contradice a [docs/AGENTS-context.md](docs/AGENTS-context.md) (contexto del PRD v0.9) o a [docs/ARQUITECTURA-DEV.md](docs/ARQUITECTURA-DEV.md), mandan esos dos y hay que avisar a Jorge para corregir este.

---

## 1. Qué es kinilum

kinilum es una **herramienta de apoyo a decisiones** para el reto *Field Shift: Adapting Farms with NASA Data* de **NASA Space Apps 2026** (hackathon del 14 al 15 de noviembre de 2026). Compara **rotaciones de cultivo** para una parcela usando observaciones de la Tierra de la NASA, datos locales y las prioridades del agricultor.

Lo que la distingue de una calculadora cualquiera:

- **Sabe cuándo no sabe.** Si dos rotaciones no se pueden distinguir con la evidencia disponible, lo dice y muestra las dos, en vez de forzar una respuesta.
- **Dice cuánto pesa cada fuente** y de dónde viene cada dato (medido, estimado o sin dato).
- **Dice qué tan estable es una sugerencia** cuando cambian el clima o las prioridades (robustez).
- **Apoya; no decide.** La última palabra es del agricultor y de su técnico local. Cierre fijo en la interfaz: *«La decisión es suya. Revísela con su técnico local.»*

### Para quién

| Quién | Descripción | Peso en las decisiones |
|---|---|---|
| **Primario** | Agricultor o agricultora de riego en el norte de Sinaloa (distrito de Guasave), maíz de otoño-invierno, **Android básico**, señal intermitente, **sin formación técnica**. | Todo texto y toda pantalla se juzgan contra esta persona. |
| Secundario | Técnico o extensionista que configura la parcela y valida reglas. | Para él es la pantalla «Ver evidencia» y los textos «a validar». |
| Demo | Jurado de Space Apps. Envío en inglés: video de hasta 30 s con subtítulos en inglés, o hasta 7 diapositivas; enlace público sin login. | Por eso existe el selector ES \| EN y la pantalla de comparación debe verse completa y pulida. |

Caso de estudio: **Guasave, Sinaloa**. El maíz de riego depende del agua de las presas, que bajó mucho: según el anuario agrícola del estado (CEIEG Sinaloa, con datos del SIAP), Sinaloa pasó de 6,656 mil toneladas de maíz en 2023 a 3,368 mil en 2024, y Guasave aportó el 27 % del total de 2024. El agua es el riesgo central y la pregunta es qué rotación gasta menos agua de riego sin perder la cosecha. (Cifras a verificar contra el SIAP antes de publicarlas.)

### Honestidad del caso (no negociable)

No hay agricultor ni caso real todavía. «Doña Rosa» es una persona ficticia de diseño. La parcela `sin-demo-001` es **de ejemplo** y se **sorteó** cerca de Guasave (semilla 20261115); nadie la eligió ni la visitó y se rotula **«Caso ilustrativo»** en todas las pantallas, el video y el envío. Todo lo que hoy se ve en la app es **dato de ejemplo escrito a mano**, incluidos los resultados por objetivo y por escenario. Nunca presentes el ejemplo como un productor real ni inventes citas, nombres, validaciones o fuentes.

---

## 2. Alcance del MVP (estricto)

- **1 región** (norte de Sinaloa, Guasave) y **1 parcela de ejemplo**.
- **6 estrategias** (cada una responde 5 preguntas):
  - **E0** — actual: maíz de riego en otoño-invierno, ciclo tras ciclo.
  - **E1** — maíz + cobertura de leguminosa en relevo (mucuna o canavalia).
  - **E2** — maíz → frijol → maíz. La variante (azufrado por defecto, que es el tipo que más se siembra en Sinaloa, o negro) la elige el técnico con `frijol_variante`; cada variante es un perfil completo del catálogo y el paquete lleva solo la elegida.
  - **E3** — maíz → sorgo → maíz.
  - **E4** — maíz → garbanzo → maíz. Se siembra en Sinaloa en invierno; sin datos locales validados.
  - **E5** — maíz → trigo → maíz. Se siembra en Sinaloa en invierno; sin datos locales validados.
- **Catálogo de cultivos de rotación:** frijol, garbanzo, sorgo y trigo, en `pipeline/rules/crops.<versión>.yaml`. Solo las leguminosas (frijol, garbanzo) suman nitrógeno. Todo lo que no tenga fuente va «a validar con el técnico»; un parámetro que falta deja su criterio «sin dato», nunca un valor inventado. Rendimiento y precio de los cuatro cultivos salen del SIAP (Guasave, otoño-invierno, riego) a nivel de municipio. Fechas de siembra, ciclo, días a floración, riegos, lámina de riego del maíz y del trigo y profundidad de raíz del maíz salen de la Agenda Técnica de Sinaloa 2017 (INIFAP), con su página y tabla (`pipeline/rules/sources/`). Lo que el documento no dice sigue «sin dato».
- **5 objetivos** con pesos predefinidos: ahorrar agua, mejorar el suelo, ingreso, reducir riesgo, equilibrado.
- **Restricciones como filtros** (equivalen a un `WHERE`, no a un peso): agua (riego o temporal), maquinaria, cultivos de rotación que acepta (frijol, garbanzo, sorgo o trigo), dónde vender y fecha de siembra. (La regla «calor extremo y suelo delgado» no aplica a Guasave y se quitó: el agua es el objetivo «Ahorrar agua», no un filtro.)
- **4 pantallas del núcleo:** Mi parcela · Comparar rotaciones · ¿Qué pasa si…? · Ver evidencia. Hay además Ajustes (idioma y tema).
- **Funciona sin señal:** PWA más un paquete de parcela en JSON precalculado (menos de 500 KB; objetivo ≈ 260 KB).
- **Idiomas:** español e inglés. Todo texto de interfaz vive en archivos de idioma; nada de cadenas sueltas en componentes.

### Fuera de alcance (no lo agregues)

Riego o alertas en tiempo real; manchas o zonas **dentro** de la parcela con datos de zona o región; IoT; login; sincronización bidireccional; precios en vivo; aprendizaje automático de punta a punta; otras regiones; **más cultivos de rotación que frijol, garbanzo, sorgo y trigo** (no se simula ninguno más); un LLM que calcule, decida o invente números o fuentes; chat libre. **No agregues más IA.** Lo que no esté en el alcance va a «Ideas post-hackathon».

### Orden de corte (si el tiempo no alcanza)

GRACE → E5 (trigo) y E4 (garbanzo) → mapa de 30 m → árbol de evidencia (queda como lista) → selector ES \| EN (quedan subtítulos) → SMAP → ECOSTRESS. **Núcleo que no se corta:** POWER, GPM, HLS, SRTM, MODIS, FAO-56, las estrategias E0–E3 × 5 preguntas, la robustez, «no podemos distinguir» y el modo avión.

---

## 3. Reglas no negociables

1. **Cinco preguntas por estrategia, en este orden:** Por qué se sugiere · Evidencia · Beneficios · Qué no sabemos · Qué revisar con su técnico.
2. **La resolución de una sugerencia nunca es más fina que la evidencia que la sustenta.** Un píxel de 30 m mezcla cultivo, borde y camino: se descarta el borde (búfer interno de 30 m).
3. **Datos de zona o región** (SMAP, GPM, POWER, GRACE) son contexto: «en su zona», nunca color dentro del polígono. POWER es clima modelado, no la lluvia de la parcela.
4. **Medido = sólido; estimado, modelado o supuesto = punteado; sin dato = diagonales.** Además, siempre con palabra e ícono (ver §7), porque el borde solo no basta con poca luz o daltonismo.
5. **Las reglas y los modelos físicos calculan** (FAO-56, umbrales). Un LLM solo puede *redactar* desde la traza; la demo funciona sin él.
6. **Degradación elegante:** si falta una fuente, el sistema sigue y dice qué falta.
7. **Memoria:** «décadas de clima y años de observación satelital», no «20 años de su parcela» (HLS a 30 m existe desde 2013; MODIS a 250 m desde 2000).
8. **Voz de la interfaz:**
   - «usted» al agricultor; «nosotros» para kinilum.
   - Frases de **20 palabras o menos**; rangos en vez de cifras exactas.
   - **Sugerir, no ordenar.** Sin emoji ni exclamaciones.
   - «kinilum» siempre en minúsculas.
   - Riesgo en **naranja con palabra e ícono**; no hay rojo, salvo el indicador «Sin señal», que va en rojo por pedido del equipo (y «Con señal» en verde), siempre con palabra e ícono.
9. **Usa el sistema de diseño kinilum** (tokens, StrategyCard, Confidence, SourceTag, Badge, Callout, Button). No inventes estilos fuera de los tokens.
10. **Privacidad:** el contorno exacto de la parcela **no se publica**. El paquete lleva solo un punto redondeado a 2 decimales y las hectáreas. El mapa de 30 m usa coordenadas locales en metros, sin ubicación ni mosaicos externos.
11. **Nunca presentes datos de ejemplo como reales.** Si una fuente falla, el paquete la declara «sin dato».

---

## 4. Cómo se decide: robustez, objetivos, restricciones

### Contrato de datos

El motor **nunca recibe un número suelto**. Cada valor trae:

```
{variable, value, p10, p90, unit, source, native_resolution, derived_resolution,
 support_level: parcel|surroundings|zone|region, timestamp,
 method: measured|interpolated|modeled|assumed, quality, assumptions[], provenance[]}
```

El contrato vive en [shared/schema/](shared/schema/README.md) (JSON Schema draft-07). Los tipos de TypeScript se **generan** de ahí en [app/src/data/schema.gen.ts](app/src/data/schema.gen.ts) con `npm run gen:schema`: no los edites a mano, y `npm run build` falla si no coinciden. Cambiar el esquema requiere la aprobación de Jorge.

### Robustez (no es probabilidad de éxito)

| Nivel | Regla | Frase en la interfaz |
|---|---|---|
| Alta | 1.er lugar en ≥ 70 % de los años simulados **y** margen mediano ≥ 10 puntos | «Se mantiene primera en casi todos los escenarios» |
| Media | 1.er lugar en 50–70 % **o** margen de 5 a 10 puntos | «Suele quedar primera, pero depende del año» |
| No podemos distinguir | 1.er lugar en < 50 % **o** margen < 5 puntos | «Con los datos que tenemos no podemos distinguir entre estas dos opciones» |

- En documentos y código se llama **robustez**. Es qué tan estable es el orden ante la incertidumbre que modelamos; **no** la probabilidad de que algo funcione en el campo (la app lo aclara en Ver evidencia).
- Los umbrales son iniciales, a calibrar.
- En «No podemos distinguir» se muestran las dos primeras y **qué dato las separaría** (por ejemplo, un análisis de la profundidad del suelo, o conocer el precio local).
- En la interfaz se dice «**9 de cada 10 años simulados**» (redondeo a décimos). El conteo exacto («450 / 500») va **solo** en Ver evidencia.
- Internamente cada «corrida» es un año simulado: toma lluvia y temperatura **juntas** de un año real del historial. En la interfaz no se usa la palabra «corridas»; se dice «años simulados».

### Objetivos y pesos

Cinco objetivos (agua, suelo, ingreso, riesgo, equilibrado) cambian el **peso** de cada criterio (agua, suelo/cobertura/nitrógeno, erosión, riesgo climático, ingreso), no los datos. Cambiar de objetivo puede cambiar el primer lugar; la app lo avisa.

### Restricciones = filtro

- Lo que no cumple sale del orden y del conteo, pero **nunca desaparece**: queda al final, con borde punteado, «No compatible con lo que nos dijo», su razón y las cinco respuestas a un toque.
- Si solo queda una opción, el veredicto dice «Con lo que nos dijo, solo su rotación actual es compatible» en vez de inventar robustez.
- Reglas de ejemplo (a validar con el técnico): el sorgo exige maquinaria (sin maquila no es viable); sembrar en julio deja sin lluvia al relevo de cobertura; sin dónde vender, frijol y sorgo salen.
- Las restricciones se aplican igual en Comparar, ¿Qué pasa si…? y Ver evidencia.
- El punto de partida lo declara el técnico en el paquete; lo que cambie el agricultor se guarda solo en su celular.

### Escenarios

normal · seco (−10 % lluvia) · muy seco (−20 %) · húmedo (+10 %) · caliente (+2 °C) · seco y caliente (−10 %, +2 °C). Cada uno con 500 corridas (años) del historial. Los controles de «¿Qué pasa si…?» saltan en pasos de 10 % y 1 °C sobre una grilla precalculada de 7×7 celdas con 100 corridas cada una; las celdas que coinciden con un escenario con nombre usan sus 500.

### Suelo y cubierta

- La profundidad efectiva de raíz para FAO-56 **no sale de SoilGrids**: ni el suelo aluvial (Guasave) ni el «sin declarar» tienen un rango con fuente, así que queda **«sin dato» hasta que el técnico la mida** (`root_depth_cm`).
- El índice de vegetación detecta «sin cubierta verde» (en la interfaz: «sin plantas verdes»), no «suelo desnudo». El riesgo de erosión combina eso con el manejo del rastrojo que declara el agricultor (se deja, se quema, se retira, se pastorea).

---

## 5. Arquitectura

```
Servidor por lotes (sin servidores en producción):
  ingesta con procedencia → armonización (grilla 0.1° y 30 m, con nivel de soporte)
  → tres entradas separadas: estado del campo · perfil de cultivos (reglas versionadas) · clima y escenarios
  → simulador de rotación: puntajes 0–100 por criterio para E0–E5 × 6 escenarios × 500 corridas
  → paquete de parcela (JSON)

Celular:
  motor de decisión (restricciones = WHERE, objetivo = pesos del ORDER BY) en cada corrida
  → robustez → traza de decisión → UI → decisión humana → registro local
```

- **Lenguajes:** Python (pipeline y simulador, NumPy vectorizado) y TypeScript estricto (motor y app). Node 24 LTS (ver `.nvmrc`). Nunca Node 20 ni Python 3.10. Lockfiles siempre. Pocas dependencias, revisadas antes de agregarlas.
- **Paquete:** lleva solo puntajes 0–100 por criterio y por corrida; **no** percentiles por criterio (impiden contar veces en primer lugar). Presupuesto en Android de gama baja: cálculo < 50 ms, pantalla < 200 ms; el control se procesa **al soltarlo**.
- **Datos de la NASA**: POWER, GPM IMERG, HLS, MODIS, SRTM/NASADEM, SMAP L4, ECOSTRESS. Mientras no lleguen, se construye contra el paquete de ejemplo.

### Estado actual del repositorio

| Carpeta | Estado |
|---|---|
| [app/](app/) | **La interfaz**, hecha a partir de los prototipos de diseño: barra inferior de vidrio, cinco pantallas y seis estrategias con datos de ejemplo. Con service worker y guardado del paquete en la Cache API (verificados en Chrome de escritorio, no en Android: ver §6); todavía sin motor y sin usar el paquete en las pantallas. |
| [docs/](docs/) | `AGENTS-context.md` y `ARQUITECTURA-DEV.md`. El PRD ágil (`.odt`) y los starter kits (`.pptx`) no están en este repositorio. |
| [shared/schema/](shared/schema/README.md) | **Esquema del contrato y del paquete** (valor, paquete, índice, configuración de parcela). Lo validan `npm run check:schema` y `pytest`. |
| [pipeline/](pipeline/README.md) | **Esqueleto.** Hechos y con pruebas: `common/`, `package/` (armar, validar y publicar el paquete) y `rules/` (catálogo `crops.v2.yaml`, todo «a validar»). `simulate/`: simulador v1 hecho (`model.py`, `run.py`): agua (ETc de FAO-56 − lluvia) e ingreso bruto (SIAP) para E0 y E2–E5; suelo, erosión, clima y E1 sin dato. `ingest/`: hecho para las fuentes abiertas (POWER, Open-Meteo, SoilGrids, escenas de HLS y Sentinel-2) y el EDA; IMERG, NASADEM, SMAP y los píxeles de HLS (NDVI de la parcela) leen valores reales con el token de Earthdata (que va en el `.env`, que git ignora); MODIS, ECOSTRESS y GRACE son esqueletos «por integrar» (el acceso a MODIS y HLS ya está confirmado con `python -m ingest.access`). `harmonize/values.py`: los seis valores del contrato listos (`rain_season`, `slope`, `tmax_may`, `soil_moisture_rootzone`, `root_depth` y `days_without_green_cover`); `values.json` sale completo. Sin Dockerfile todavía. Hallazgos de la primera corrida real en [docs/EDA-hallazgos.md](docs/EDA-hallazgos.md). |

No hagas commit ni push sin que el usuario lo pida.

### Equipo

Tres personas: Jorge, Isis e Isabella. Sin módulos asignados: cualquiera toma cualquier parte (contrato, ingesta, simulador, motor, app, despliegue). Los cambios en `shared/schema/` requieren la aprobación de Jorge. Código abierto (licencia por decidir: Apache-2.0 o MIT). Los asesores externos firman una carta de consentimiento; no publiques su nombre.

---

## 6. La app (`app/`)

> **Estado en este repositorio (15 de noviembre de 2026).** «Pila», «Comandos», «Estructura», «Rutas» y «Las pantallas» describen lo que hay hoy. **Modo avión: construido y verificado en Chrome de escritorio (15 de noviembre de 2026); sin probar en Android.** Hay service worker (`sw/sw.template.js`), guardado y relectura del paquete (`src/offline/`), indicador «Con señal / Sin señal» y los dos avisos de versión nueva. Lo verifican `npm test` (lógica del paquete y del service worker, simulados), `npm run build` (`scripts/check-offline.mjs`) y una prueba a mano en Chrome con `build` + `preview` en un origen limpio: registro, precache de 12 archivos, «Listo para usar sin señal», recarga con el servidor apagado, y los dos avisos aplicándose solo al aceptar. **Falta Android real** (y Safari/Firefox). El panel integrado de Claude no admite service workers: ahí se ve «Este navegador no guarda la aplicación». **Por `http` fuera de localhost (por ejemplo, la IP de Tailscale) el navegador no tiene Cache API ni service worker:** los datos se bajan y se ven, pero solo en memoria, y la tarjeta de Ajustes dice «Este navegador no guarda los datos» (nunca «Listo»). **Para probar el modo avión, use un puerto o perfil limpio:** un service worker o una caché de otra versión en el mismo `localhost:<puerto>` contamina la prueba. «Listo para usar sin señal» dice que el paquete y la app están guardados. **Idioma:** hay selector ES \| EN en Ajustes (`src/i18n/lang.tsx`, `en.ts`, `strategies.en.json`; se guarda en `kinilum.lang`); una prueba vigila que ambos idiomas tengan las mismas claves. «Mi parcela» **lee el paquete guardado** (valores reales de Guasave). Comparar, ¿Qué pasaría si…? y Evidencia **ordenan con las corridas del bloque `simulation` del paquete** (`data/simulation.ts`) y lo dicen en pantalla («Calculado con datos de su zona»). «¿Qué pasaría si…?» agrega **«Con menos agua de riego»**: un control de 100 a 40 % del agua que hoy pide el maíz solo (`data/irrigation.ts`, desde `water_mm` de cada celda) y qué parte de lo que pide cada opción alcanzaría a cubrir, en un año muy seco, uno típico y uno húmedo. Es agua que se pide, no rendimiento: el rendimiento con recorte no se calcula; solo si el paquete no trae `simulation` caen al **ejemplo escrito a mano** de `data/scenarios.ts` y lo rotulan «Ejemplo ilustrativo». Siguen sin construir: mapa de 30 m, manifiesto para «Instalar» y barra lateral en escritorio (el indicador va en el encabezado). De lo guardado en el celular hoy: `kinilum.theme` y `kinilum.package.<id>`.

### Pila

Vite 7 · React 18.3 · TypeScript 5.9 estricto (`noUncheckedIndexedAccess`) · Radix Primitives (toggle-group, collapsible, slider). Fuentes: Geist, DM Sans y Geist Mono, locales (`.woff2`), sin CDN. Pruebas de datos con `node --test` (Node carga los `.ts` sin compilar).

### Comandos (desde `app/`)

```bash
npm run dev          # servidor de desarrollo en :5173
npm test             # pruebas de datos: catálogo, reglas, seis estrategias, textos (tests/data.test.mjs)
npm run build        # tipos del esquema al día + npm test + tsc -b + vite build + esquema
npm run preview      # sirve dist/ en :4173
npm run typecheck    # tsc -b
npm run check:schema # paquetes publicados contra shared/schema/ + autoprueba
npm run gen:schema   # regenera src/data/schema.gen.ts desde shared/schema/
```

En el repo, `.claude/launch.json` define `kinilum-app` (dev, 5173).

### Estructura de `app/src`

| Ruta | Qué contiene |
|---|---|
| `main.tsx` | Raíz: `ThemeProvider › AppShell › AppStateProvider › pantalla`. |
| `offline/` | `packageStore.ts` (bajar, guardar, **releer**, avisar de datos nuevos; sin React), `shell.ts` (registro y estado del service worker), `connectivity.ts` (con señal / sin señal con prueba al sitio), `readiness.ts` (cuándo sí se puede decir «Listo»), `OfflineProvider.tsx` y `Offline.tsx` (insignia, avisos y la tarjeta de Ajustes). |
| `shell/` | `AppShell` (encabezado, escenario con deslizamiento entre secciones), `TabBar` (barra inferior de vidrio con resorte), `icons.tsx`, `state.tsx` (objetivo, estrategia elegida, clima y lo declarado), `theme.tsx` (claro, oscuro o dispositivo), `useFlip.ts` (animación de reorden). |
| `screens/` | `MiParcela`, `Comparar`, `QuePasaSi`, `Evidencia`, `Ajustes` y su CSS. |
| `ds/` | **Sistema de diseño:** `tokens.css` (copiado tal cual del sistema), `components.css/.tsx`, `primitives.*` (envoltorios de Radix), fuentes. |
| `data/` | `comparison.ts` (estrategias E0–E5, criterios, objetivos, robustez), `crops.ts` (espejo del catálogo de cultivos), `restrictions.ts` (reglas de restricción y lo declarado), `scenarios.ts` (modelo de ejemplo sobre la grilla de 49 celdas), `schema.gen.ts` (tipos **generados** del esquema). Sus imports llevan `.ts` para que las pruebas los carguen con Node. |
| `i18n/` | `es.ts` (textos de la interfaz; todavía sin inglés), `strategies.es.json` y `strategies.en.json` (las cinco respuestas de E0–E5, variantes de frijol y reglas de cultivo, con las mismas claves), `strategies.ts`. |

### Rutas

Por hash, para funcionar en cualquier hosting estático: `#/<pantalla>` con pantallas `parcela`, `comparar`, `simular`, `evidencia` y `ajustes`. Todavía sin identificador de parcela en la ruta: solo existe la de ejemplo, `sin-demo-001`.

Ejemplo: `http://localhost:5173/#/comparar`.

### Las pantallas

1. **Mi parcela** — ficha de la parcela, tres datos con su fuente (meses sin cubierta, lluvia, suelo), «Qué no sabemos» y «Lo que nos dijo» (maquinaria, cultivos que acepta y dónde vender).
2. **Comparar rotaciones** — la más importante y la que verá el jurado. Objetivo (chips) → seis tarjetas en una columna, con sus cinco criterios → las cinco preguntas debajo de la opción que se toca. Las que no tienen datos para el objetivo y las excluidas van al final, con su razón; ninguna se oculta.
3. **¿Qué pasaría si…?** — controles de lluvia y calor sobre la grilla de 49 celdas y el orden de las seis opciones, que se reacomoda. Es un escenario, **no un pronóstico**.
4. **Evidencia** — robustez con conteo exacto, la variante de frijol simulada y quién la eligió, las reglas de cultivo con «A validar con el técnico» y las fuentes.
5. **Ajustes** — tema.

### El paquete de la parcela

`app/public/packages/index.json` apunta al archivo vigente; el archivo se llama `<id>.<fecha>.json` (si se regenera el mismo día, `.r2`, `.r3`…). **Si cambias el contenido, cambia el nombre**: así ningún celular mezcla uno nuevo con uno viejo en caché. El paquete actual es `sin-demo-001.2026-11-15.r3.json` (≈ 293 KB con la simulación, formato `kinilum-package/2`, cumple `shared/schema/`) y **sale de datos reales** (`python -m ingest.run` y `python -m package.build`, ver `docs/EDA-hallazgos.md`): los seis valores, lluvia de la temporada, cubierta por mes, temporadas (falta de agua y calor en la floración), umbrales, normales, restricciones del técnico y el bloque `rotation`. **Sin mapa de 30 m todavía** (`map_30m` es opcional). **Con el bloque `simulation`** (puntajes por corrida de agua e ingreso; ver `pipeline/simulate/run.py`), que la app usa para ordenar las rotaciones. La app rechaza un `package_format` que no conoce y vuelve a descargarlo.

### Modo avión: cómo funciona y la trampa conocida

- El **shell** (HTML, JS, CSS, fuentes, marca) lo precachea el service worker. `scripts/build-sw.mjs` (después de `vite build`) arma `dist/sw.js` desde `sw/sw.template.js` con la lista de archivos y una versión por contenido; sin plugins de PWA.
- El **paquete JSON NO** va en el precache: lo guarda la app en la Cache API (`kinilum-packages-v1`) y **lo vuelve a leer** antes de mostrar «Listo para usar sin señal». Primera vez sin señal: la puerta explica que hace falta señal una sola vez; nunca dice «Listo».
- Hay un aviso «Hay datos nuevos» y otro «Hay una versión nueva de kinilum»; ninguno cambia nada sin que el usuario acepte. Los datos nuevos se bajan y verifican antes de soltar los viejos; la versión nueva del service worker espera hasta que el usuario toca «Actualizar».
- **«Listo para usar sin señal» exige dos cosas:** el paquete guardado y releído (idéntico byte a byte) **y** la app guardada (el `index.html` se lee de la caché). Si falta una, se dice cuál: «Este navegador no guarda la aplicación», «Hace falta señal una sola vez» o «No pudimos guardar los datos». Un formato de paquete desconocido se rechaza y, si ya estaba guardado, se descarta para volver a bajarlo.
- **Si el service worker da problemas en producción:** el índice y el paquete nunca pasan por él, y solo se registra en el build. Para quitarlo, publicar un `sw.js` que llame a `registration.unregister()` y vacíe las cachés `kinilum-shell-*`.
- **Indicador «Con señal / Sin señal»** (verde / rojo, ver §3) siempre a la vista (encabezado en móvil, barra lateral en escritorio, también en Ajustes). No usa solo `navigator.onLine`: además prueba si el sitio responde (al abrir, al volver a la pestaña, con los eventos `online`/`offline` y cada minuto con la pantalla a la vista). Sin señal va en rojo y con señal en verde (tokens `--offline` en `offline.css`; antes iba en azul informativo).
- **`npm run dev` no registra el service worker.** El modo avión **solo se prueba con `npm run build` + `npm run preview`**, apagando el servidor o poniendo el navegador sin conexión. En `dev` el paquete siempre se descarga fresco, y la insignia dice «Desarrollo: sin modo avión».
- `scripts/check-offline.mjs` falla el build si algún archivo de `dist/` (JS, CSS, fuentes, marca; incluido el del mapa cuando exista) queda fuera del precache, si el paquete excede 500 KB, si lleva polígono o coordenadas, o si el nombre no lleva parcela y fecha.

### Almacenamiento local (todo es por celular, nada sale)

`kinilum.lang` · `kinilum.theme` · `kinilum.objective` (por defecto `soil`) · `kinilum.stubble` · `kinilum.restrictions` · `kinilum.package.<id>` (puntero al archivo en caché; el archivo está en la Cache API, `kinilum-packages-v1`). Hoy se guardan `kinilum.theme`, `kinilum.lang` y `kinilum.package.<id>`. **Importante para probar:** el empate «No podemos distinguir» solo aparece con el objetivo **Equilibrado**; el valor guardado en `kinilum.objective` cambia lo que ve cada sesión.

---

## 7. Cómo se ve y cómo se escribe

### Jerarquía de cada dato (decisión de diseño de esta etapa)

Cada tarjeta de «Lo que sabemos» se lee en dos pasos:

1. **Esquina:** de dónde viene el dato, con un **número de fuente fijo**: «(1) NASA HLS 30 m». Se numera por fuente, no por tarjeta; el mismo número aparece en Fuentes, en Ver evidencia y en la evidencia de las tarjetas de Comparar. El registro vive en [app/src/data/sources.ts](app/src/data/sources.ts) (1 HLS, 2 GPM IMERG, 3 POWER, 4 Técnico y agricultor, 5 SMAP, 6 MODIS, 7 FAO-56, 8 SRTM…).
2. **Cuerpo y pie:** primero la **frase que dice qué significa** (20 px, negrita: «Unos 3 meses y medio al año la tierra queda sin plantas verdes»), después la etiqueta, el **número como apoyo** con su rango, y al pie **una sola palabra de método con ícono**:

| Sello | Ícono | Cuándo |
|---|---|---|
| Medido | círculo lleno | satélite o campo directo |
| Estimado | círculo punteado | modelado, interpolado o satélite con cálculo (GPM, POWER) |
| Supuesto · falta medirlo | círculo punteado | supuesto del equipo; dice qué hacer para mejorar el dato |
| Sin dato · la fuente no respondió | cuadro rayado | la fuente falló |

La lluvia de GPM IMERG se rotula **estimada**, no medida: IMERG es una estimación hecha con satélites. La diferencia fina entre «estimado por satélite» y «modelado» vive en Ver evidencia.

### Lenguaje llano (lo que más cuesta mantener)

La persona usuaria no es técnica. Vocabulario acordado: «plantas verdes» (no «cubierta verde»), «tierra sobre la piedra» (no «profundidad del suelo»), «años simulados» (no «corridas»), «orilla que no usamos» (no «borde descartado»), «Calculado o supuesto, no medido» (no «modelado, interpolado o supuesto»). Los meses se dicen en meses («unos 3 meses y medio»), no en días. Lo que esté en un archivo de idioma se cambia **en `es.json` y `en.json` a la vez** (TypeScript marca las claves que falten).

### Tamaños y legibilidad

Pensado para un Android barato bajo el sol: cuerpo mínimo **14 px**, texto secundario mínimo **12 px**, la frase principal de cada tarjeta 20 px. En teléfono las tarjetas van en **una columna**. Hay 120 px de espacio al pie para que el menú flotante no tape el contenido.

### Navegación

Menú único con dos presentaciones según el ancho del navegador: píldora flotante de vidrio abajo con un indicador que se desliza (< 900 px) y barra lateral incrustada con grupos (Conocer, Decidir, Confiar, Preferencias) y el estado sin señal al pie (≥ 900 px). **No uses `overflow: hidden` en `html`, `body` ni `.kn-app`**: rompe los elementos fijos; para cortar lo que se sale de lado, usa `overflow-x: clip`. El elemento activo del menú lateral usa solo el color de énfasis (sin fondo).

### Tema

Oscuro primero (`data-theme="dark"` en `<html>`, con script en `index.html` para no parpadear); hay tema claro y «Dispositivo» (sigue al sistema). `kinilum.theme` guarda `dark`, `light` o `system`. Colores solo con tokens de `ds/tokens.css`.

---

## 8. Convenciones de código

- **Textos:** nada de cadenas sueltas en componentes; los de interfaz van en `i18n/es.ts` y los de estrategias, variantes y reglas en `strategies.es.json` y `strategies.en.json`, a la vez y con las mismas claves.
- **Estilos:** solo tokens (`var(--…)`); CSS junto a cada pantalla o pieza. No copies valores de color o tamaño.
- **Componentes de Radix:** las pantallas nunca importan Radix directo; se usan las envolturas de `ds/primitives.tsx`.
- **Archivos:** guarda en **UTF-8** (el proyecto tiene tildes y ñ). Ha habido comentarios con tildes rotas por codificación.
- **Fixtures vs. motor:** hoy los resultados son de ejemplo en `data/scenarios.ts`. Cuando llegue el motor, devolverá **la misma forma** (`ScenarioResult`: las que compiten, las que no tienen datos y las excluidas) y esos archivos se borran. No acoples pantallas a los detalles del modelo de ejemplo.
- **Piezas fuera del sistema de diseño** que hay que llevar de vuelta: `SourceLine`, `MethodStamp`, `SourceRef`, `SourceList`, los ajustes locales de `StrategyCard` en móvil y el verde de la grilla de cubierta.
- **Seguridad y privacidad:** sin claves, sin analítica, sin tipografías ni mosaicos externos, sin coordenadas precisas. Si agregas una dependencia, justifícala.
- **No hagas commit ni push** salvo que lo pidan. Si lo hacen, sin líneas de atribución en el mensaje.

---

## 9. Cómo verificar un cambio

1. `npm run typecheck` (desde `app/`).
2. `npm run dev` y revisar la pantalla en el navegador, **en 375 px y en escritorio**, en tema claro y oscuro.
3. `npm run build` (incluye las pruebas de datos y la revisión del esquema) y, si tocaste el pipeline o el contrato, `pytest` desde `pipeline/`.
4. Si tocaste el catálogo, la parcela o el contrato: `npm test` falla si la app dejó de decir lo mismo que `pipeline/rules/` y el paquete publicado.
5. Revisar que no haya scroll horizontal y que ningún texto quede bajo el menú flotante.
6. Para las frases de la interfaz: ¿las entendería una persona sin formación técnica?

---

## 10. Pruebas con usuarios simulados (`launch-qa` + Playwright)

Se instaló la skill `launch-qa` (en `.agents/skills/launch-qa`, enlazada para Claude Code). Lanza subagentes que recorren la app en un navegador real, cada uno con un perfil, y devuelven hallazgos con capturas. **Requiere un MCP de navegador (Playwright o Chrome DevTools) en la sesión**; si las herramientas no aparecen, hay que reiniciar Claude Code tras `claude mcp add playwright -- npx @playwright/mcp@latest`.

### Reglas del ejercicio

- **Navegador real y capturas reales.** Un hallazgo sin captura no cuenta. Los personajes reportan lo que ven, no lo que dice el código.
- **Contexto aislado por usuario.** El estado vive en `localStorage` del navegador; un contexto nuevo por usuario evita que se mezclen objetivo, restricciones y rastrojo.
- **Sin sesión ni cuentas:** no hay login. La URL de entrada es `…/#/p/sin-demo-001/parcela`.
- **Servidor:** `npm run dev` (5173) sirve para casi todo; **el modo avión, la instalación y el service worker solo se prueban en `npm run preview` (4173)**.
- **Los personajes no leen el código.** Evalúan la interfaz como la vería esa persona. Quien coordina la prueba arregla errores de código y **propone** los cambios de texto y de flujo para que el usuario los apruebe antes de aplicarlos.
- **Lo que no se puede probar se dice.** Sin pantalla bajo el sol, sin celular real ni red lenta real, se anota.

### Primer éxito

Que una persona agricultora llegue a **Comparar rotaciones**, entienda **qué se le sugiere considerar y qué tan seguro es**, y sepa qué revisar con su técnico.

### Los cinco usuarios

Cada uno es un modelo de Claude que **actúa** como esa persona. Todos parten de la URL de la parcela, en teléfono (375 × 812) salvo que se diga otra cosa, y todos recorren las cuatro pantallas.

1. **Doña Rosa, agricultora (personaje de diseño).** Productora de riego de unos 50 años, usa WhatsApp y poco más, **no tiene formación técnica**, lee despacio y desconfía de lo que no entiende. Solo conoce palabras del campo: «riego», «presa», «siembra», «rastrojo». Quiere saber: ¿qué me conviene sembrar y por qué? Marca todo término que no entendería («robustez», «modelado», «resolución», «NASA GPM IMERG 0.1°»), cada frase de más de 20 palabras y cada lugar donde no sabría qué tocar.
2. **El técnico extensionista.** Conoce FAO-56, NDVI y rotaciones de cultivo. Busca **procedencia y honestidad**: ¿de dónde sale cada número?, ¿se distingue lo medido de lo supuesto?, ¿lo que no se sabe está dicho?, ¿las reglas de restricción tienen sentido agronómico? Evalúa Ver evidencia, «Qué no sabemos» y los numerales de fuentes.
3. **La persona impaciente en un celular barato.** Hojea, no lee párrafos, toca el primer botón que parece correcto, se va al primer problema o espera de más de 3 segundos. Registra el momento exacto en que se habría ido y qué le haría falta ver en la primera pantalla sin hacer scroll. Prueba con red lenta, sin señal (`npm run preview`) y en horizontal.
4. **El jurado de Space Apps (anglohablante, 3 minutos).** Abre la app, cambia a **EN**, y quiere entender en un minuto el problema, el uso de datos de la NASA y qué hace distinto a kinilum. Evalúa si la traducción suena natural (no a texto traducido), si el «caso ilustrativo» queda claro y si **«No podemos distinguir»** se nota como diferenciador. Para encontrarlo debe elegir el objetivo **Equilibrado** en Comparar.
5. **La persona que intenta romperlo (y accesibilidad).** Cambia de objetivo y de restricciones sin parar, deja a una sola opción compatible, mueve los controles de «¿Qué pasa si…?» al extremo, vuelve atrás con el botón del navegador, recarga en cada paso, abre dos pestañas, usa solo teclado y lector de pantalla (nombres accesibles, foco visible, orden de tabulación), tema claro y oscuro, zoom al 200 %, y contraste en condiciones de poca luz.

### Qué debe entregar cada uno

Una lista de hallazgos (no una narración), con este formato:

```
- pantalla / paso: <dónde>
  qué: <una frase: qué vio o qué no pudo hacer>
  severidad: bloqueo | fricción | confusión
  tipo: error | texto | flujo | diseño
  captura: <ruta>
  esperaba: <qué esperaba que pasara>
  propuesta: <cambio concreto, en el tono de la interfaz>
```

Además, una calificación del 1 al 5 de **qué tan fácil fue** y una respuesta corta a: *«Con tus palabras, ¿qué hace esta aplicación y qué te recomienda hacer?»* (si no puede decirlo, ese es el hallazgo más importante).

### Después de la prueba

Se unen los hallazgos en una sola lista ordenada por severidad y por cuántos usuarios los vieron. Los **errores** se corrigen. Los cambios de **texto, flujo y diseño** se proponen en una línea cada uno y **solo se aplican los que apruebe el usuario**. Se vuelve a pasar a los mismos usuarios para confirmar; solo cuenta como arreglado lo que ya ninguno reproduce.

---

## 11. Pendientes conocidos (acumulados)

**Datos y contenido**
- Todo es de ejemplo: valores de tarjetas, mapa, contorno, normales de lluvia y calor, resultados por objetivo y por escenario. Se borra cuando lleguen el motor y la grilla real.
- Reglas de restricción y cortes de «tierra sobre la piedra» (< 30 cm «poca», > 60 cm «profunda») son hipótesis a validar con un técnico de la región. El control de agua no excluye nada en este ejemplo (la parcela es de riego).
- Textos de las tarjetas: borrador del PRD; los de E0 los escribió el equipo de desarrollo.
- La línea «Lluvia de esta temporada» sigue dibujada sólida (ahí significa «ya llovió»); su fuente sí dice «Estimado».
- Los rangos normales todavía no aparecen en Ver evidencia.

**Lo que falta del PRD**
- Cadena de evidencia (HU4.3): espera la traza del motor.
- Registro de la decisión (EP6, prioridad P1).
- Ver evidencia no refleja el escenario elegido en «¿Qué pasa si…?».
- Pasada de lenguaje llano en Comparar (sobre todo el veredicto) y pruebas reales con agricultores o técnicos.
- **Probar el modo avión en Android real** (`npm run build` + `npm run preview`, apagar el servidor o poner el teléfono sin conexión; «Instalar» pide además un manifiesto con íconos de 192 y 512 px, que no existe); rendimiento; publicar en GitHub Pages; etiqueta de política de contenido (CSP) limitada al propio sitio.

**Técnico**
- La app valida poco al cargar el paquete (solo el formato); la validación completa corre en el pipeline y en `npm run check:schema`.
- El simulador v1 solo calcula agua e ingreso bruto. Faltan suelo (nitrógeno), erosión y clima, por falta de datos; con eso hoy solo ordenan los objetivos «Ahorrar agua» e «Ingreso». Las 500 corridas salen de **9 años reales** de clima (2016–2024) combinados con fechas de siembra y años de rendimiento y precio: la robustez que muestra es optimista; por eso la app nunca dice «10 de cada 10». Más calor acorta el ciclo del maíz (grados día), así que baja el agua que pide: es el modelo, no un error.
- `pipeline/`: sin Python en esta máquina las pruebas se corrieron con Pyodide (24 pasan); falta `requirements.txt` con sumas de verificación y el Dockerfile.
- El motor debe devolver la misma forma que el ejemplo y las estrategias excluidas.
- Leaflet se usa directo (react-leaflet 5 pide React 19); en celular el mapa no se arrastra para no atrapar el scroll.
- 6 vulnerabilidades bajas o moderadas en herramientas de compilación (lo que se publica tiene 0).
- Git no está en el PATH de esta máquina: se usa el de GitHub Desktop.

---

## 12. Cuando dudes

Elige lo más simple que mantenga la demo de punta a punta, real y sin señal. Si algo no está en el alcance, va a «Ideas post-hackathon». Si tienes que elegir entre una frase técnica precisa y una que entienda doña Rosa, gana la que ella entienda, y el detalle técnico se manda a Ver evidencia.
