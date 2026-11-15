# kinilum — contexto global para agentes (PRD v0.9)

## Misión
kinilum es una herramienta de apoyo a decisiones para el reto "Field Shift: Adapting Farms with NASA Data" (NASA Space Apps 2026, 14–15 nov 2026). Compara rotaciones de cultivo para una parcela usando observaciones de la Tierra de la NASA, datos locales y las prioridades del agricultor. Sabe cuándo tiene evidencia suficiente, cuánto pesa cada fuente y qué tan estable es una sugerencia cuando cambian el clima o las prioridades. Apoya; no decide. La última palabra es del agricultor y de su técnico local.

## Usuario
- Primario: agricultor/a de temporal en Yucatán (sur del estado, municipio por confirmar), 3–10 ha, milpa y maíz, Android básico, señal intermitente, sin formación técnica.
- Caso de estudio: calor extremo, suelo delgado sobre roca caliza (tsek'el pedregoso, k'ankab rojo), lluvias concentradas. El calor es el riesgo central; ECOSTRESS está en P0.
- Secundario: técnico o extensionista que configura la parcela y valida reglas.
- Demo: jurado de Space Apps. Envío en inglés: video de hasta 30 s con subtítulos en inglés o hasta 7 diapositivas; enlace público al proyecto sin login; datos de la NASA usados; declaración de uso de IA (confirmar guía 2026).

## Alcance del MVP (estricto)
- 1 región (Yucatán), 1 parcela de ejemplo (polígono dibujado por el equipo en una zona agrícola representativa; no es el terreno de una persona identificada), 6 estrategias: E0 actual (maíz de temporal, suelo desnudo en secas), E1 maíz + cobertura de leguminosa en relevo, E2 maíz -> frijol regional -> maíz (variante xpelón por defecto, ib o negro; la elige el técnico con `frijol_variante` y cada una es un perfil completo), E3 maíz -> sorgo -> maíz, E4 maíz -> garbanzo -> maíz, E5 maíz -> trigo -> maíz. Garbanzo y trigo son poco comunes en la zona y no tienen datos locales validados.
- Catálogo de cultivos de rotación versionado (`pipeline/rules/crops.<versión>.yaml`): frijol, garbanzo, sorgo y trigo. Solo las leguminosas suman nitrógeno. Lo que no tiene fuente va «a validar con el técnico»; un parámetro que falta deja su criterio «sin dato».
- Objetivos con pesos predefinidos: ahorrar agua, mejorar suelo, ingreso, reducir riesgo, equilibrado.
- Restricciones como filtros: agua (temporal/riego), maquinaria, cultivos de rotación aceptados (frijol, garbanzo, sorgo, trigo), mercado accesible, fecha de siembra. Con calor extremo y suelo delgado, garbanzo y trigo se marcan «poco viable».
- Pantallas: Mi parcela · Comparar rotaciones · ¿Qué pasa si...? · Ver evidencia.
- Funciona sin señal: PWA + paquete de parcela JSON precalculado (< 500 KB; objetivo ≈ 260 KB).
- Idiomas: todo texto de interfaz vive en archivos de idioma (es, en) desde el primer commit; nada de cadenas sueltas en componentes. Selector ES | EN.

## Fuera de alcance
Riego o alertas en tiempo real; manchas o zonas dentro de la parcela con datos de zona o región (SMAP, GPM, POWER, GRACE); IoT; login; sincronización bidireccional; precios en vivo; ML entrenado de punta a punta; otras regiones; más cultivos de rotación que frijol, garbanzo, sorgo y trigo (no se simula ninguno más); un LLM que calcule, decida, invente números o fuentes; chat libre. No agregues más IA.

## Arquitectura
Servidor por lotes: ingesta con procedencia -> armonización (grilla 0.1° y grilla 30 m) con nivel de soporte -> tres entradas separadas: estado del campo, perfil de cultivos (reglas versionadas con fuente), clima y escenarios -> simulador de rotación: puntajes 0-100 por criterio (agua, suelo/cobertura y nitrógeno, erosión, riesgo climático, ingreso) para E0-E3 × 6 escenarios × 500 corridas -> paquete de parcela.
Celular: motor de decisión (restricciones = WHERE, objetivo = pesos del ORDER BY) en cada corrida -> robustez (veces en 1.er lugar, margen mediano frente a la 2.a, sensibilidad) -> traza de decisión -> UI (y LLM opcional que solo redacta la traza) -> decisión humana -> registro local.

## Contrato de datos (cada valor)
`{variable, value, p10, p90, unit, source, native_resolution, derived_resolution, support_level: parcel|surroundings|zone|region, timestamp, method: measured|interpolated|modeled|assumed, quality, assumptions[], provenance[]}`. El motor nunca recibe un número suelto.

## Robustez (no es probabilidad de éxito)
- Alta: 1.er lugar en >= 70 % de las corridas y margen mediano >= 10 puntos.
- Media: 1.er lugar en 50-70 % o margen de 5 a 10 puntos.
- No podemos distinguir: 1.er lugar en < 50 % o margen < 5 puntos -> mostrar las dos primeras y qué dato las separaría.
Umbrales iniciales, a calibrar. En documentos y código se llama robustez. En la interfaz: "Se mantiene primera en casi todos los escenarios" / "Suele quedar primera, pero depende del año" / "Con los datos que tenemos no podemos distinguir entre estas dos opciones". La certeza de un dato individual sigue con el componente Confidence.

## Paquete y desempeño
El paquete lleva solo puntajes 0-100 por criterio y por corrida (matriz principal 6×500×4×5 ≈ 60 KB; grilla de controles 7×7×100×4×5 ≈ 100 KB). No uses percentiles por criterio: impiden contar las veces en primer lugar. Presupuesto en Android de gama baja: cálculo < 50 ms, pantalla < 200 ms; el control se procesa al soltarlo; Web Worker si hace falta. Plan B: 200 corridas por escenario.

## Orden de corte (si el tiempo no alcanza)
GRACE -> E5 (trigo) y E4 (garbanzo) -> mapa 30 m -> árbol de evidencia (queda como lista) -> selector ES | EN (quedan subtítulos) -> SMAP -> ECOSTRESS. Núcleo que no se corta: POWER, GPM, HLS, SRTM, MODIS, FAO-56, estrategias E0–E3 × 5 preguntas, robustez, «no podemos distinguir», modo avión.

## Suelo y cubierta
- La profundidad efectiva de raíz para FAO-56 NO sale de SoilGrids: tsek'el 15-25 cm, k'ankab 40-60 cm, sin declarar 15-60 cm (rangos a validar); una medición de campo reemplaza el rango.
- El índice de vegetación detecta "sin cubierta verde", no "suelo desnudo". El riesgo de erosión combina cubierta verde con el manejo del rastrojo que declara el agricultor (se deja, se quema, se retira, se pastorea).

## Sensibilidad y consistencia
- Sensibilidad en el celular: criterio i que maximiza |w_i × mediana(puntaje_i(1.a) − puntaje_i(2.a))| sobre las corridas; plantilla fija "La diferencia viene sobre todo de {criterio}". El dato detrás lo precalcula el servidor.
- En la UI la robustez se dice "9 de cada 10 corridas" (redondeo a décimos); el conteo exacto va solo en "Ver evidencia". Las celdas de la grilla que coinciden con un escenario con nombre usan sus 500 corridas.

## Escenarios
normal · seco (-10 % lluvia) · muy seco (-20 %) · húmedo (+10 %) · caliente (+2 °C) · seco y caliente (-10 %, +2 °C). Dentro de cada uno, 500 corridas que toman años completos del historial (lluvia y temperatura juntas) y muestrean rangos de suelo, cultivo, rendimiento y precio. Los controles de la pantalla "¿Qué pasa si...?" saltan en pasos de 10 % y 1 °C sobre una grilla precalculada.

## Reglas no negociables
1. Cada estrategia responde las cinco preguntas, en orden: Por qué se sugiere · Evidencia · Beneficios · Qué no sabemos · Revisar con un experto local.
2. La resolución de una sugerencia nunca es más fina que la evidencia que la sustenta. Un píxel de 30 m también mezcla cultivo, borde y camino: se descarta el borde (búfer interno de 30 m).
3. Datos de zona o región (SMAP, GPM, POWER, GRACE) son contexto: "en su zona", nunca color dentro del polígono. POWER es clima modelado, no la lluvia de la parcela.
4. Medido = sólido; estimado/modelado/supuesto = punteado; sin dato = patrón diagonal.
5. Las reglas y los modelos físicos calculan (FAO-56, umbrales). El LLM solo redacta desde la traza; la demo funciona sin él.
6. Degradación elegante: si falta una fuente, el sistema sigue y dice qué falta.
7. Memoria: "décadas de clima y años de observación satelital", no "20 años de su parcela" (HLS a 30 m existe desde 2013; MODIS 250 m desde 2000).
8. Voz de UI: usted al agricultor, nosotros para kinilum; frases de 20 palabras o menos; rangos; sugerir, no ordenar; sin emoji ni exclamaciones; "kinilum" en minúsculas; riesgo en naranja con palabra e ícono, no hay rojo. Cierre: "La decisión es suya. Revísela con su técnico local."
9. Usa el sistema de diseño kinilum (StrategyCard, Confidence, SourceTag, Badge, Callout, Button). Documentos: sección "Documentos" del sistema de diseño.

## Honestidad del caso
No hay agricultor ni caso real todavía. "Doña Rosa" es una persona ficticia de diseño; la parcela es de ejemplo y se rotula "caso ilustrativo" en la demo, el video y el envío. Los datos de satélite son reales para esa zona; suelo, rastrojo, maquinaria y mercado son supuestos (`method: assumed`). Nunca presentes el ejemplo como un productor real ni inventes citas, nombres o validaciones. El contorno exacto no se publica: el paquete lleva solo un punto redondeado a 2 decimales y las hectáreas (ver ARQUITECTURA-DEV.md, sección 5.3).

## Datos de la NASA
Mientras no lleguen los datos de la NASA: construir contra el paquete de ejemplo escrito a mano y probar la ingesta con respuestas simuladas (`pipeline/tests/fixtures/`). Al pedirlos, primero HLS y MODIS (hacen fila), luego POWER, GPM y SRTM. Si una fuente no llega, el paquete la declara «sin dato»; si nada real llega, se rotula como ejemplo. Nunca presentar datos de ejemplo como reales.

## Equipo, flujo y licencia
- Tres personas (Jorge, Isis e Isabella), sin módulos asignados: cualquiera toma cualquier parte. El código sigue en carpetas separadas por módulo.
- El contrato de datos y el paquete de ejemplo son lo primero; todos trabajan contra ellos. Los cambios en `shared/schema/` requieren la aprobación de Jorge.
- Integración por pull request fusionado por quien lo abre cuando pasa la verificación automática (esquema, pruebas, compilación, revisión de privacidad). Una IA de revisión comenta, nunca aprueba.
- El proyecto es de código abierto (licencia por decidir: Apache-2.0 o MIT). No hay acuerdo de confidencialidad. Los asesores externos firman una carta de consentimiento; no se publica su nombre sin permiso por escrito.
- No se reutiliza código de proyectos previos.

## Lenguajes, versiones y dependencias
- Dos lenguajes: Python (pipeline y simulador con NumPy vectorizado) y TypeScript estricto (motor y app). No hay servidores. No cambies de lenguaje sin una medición que lo justifique.
- Solo versiones con soporte de seguridad: Python 3.14 (alternativa 3.13) y Node 24 LTS (alternativa 22). Nunca Node 20 ni Python 3.10. Versiones fijadas en `.nvmrc` y `.python-version`; lockfiles siempre; imagen de Docker fijada por digest.
- Pocas dependencias, revisadas antes de agregarlas. Dependabot y secret scanning activos. Sin claves en el repositorio ni en la imagen.

## Cuando dudes
Elige lo más simple que mantenga la demo de punta a punta, real y sin señal. Lo que no esté en el alcance va a "Ideas post-hackathon".
