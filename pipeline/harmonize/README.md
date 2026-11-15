# harmonize — de bronce a plata

Pone todo en las mismas grillas y le da a cada valor su **nivel de soporte**.

- Grillas de **0.1°** (zona y región) y de **30 m** (parcela).
- **Búfer interno de 30 m**: un píxel de 30 m mezcla cultivo, borde y camino; se descarta el borde. De aquí sale `clean_pixels`.
- **`support_level`** de cada valor: `parcel` (HLS, SRTM, lo declarado), `surroundings` (MODIS a 250 m), `zone` (GPM, SMAP) y `region` (POWER). Los datos de zona y región son contexto («en su zona»), nunca color dentro del polígono.
- **Profundidad de raíz para FAO-56:** sale de lo declarado por el técnico (tsek'el 15–25 cm, k'ankab 40–60 cm, sin declarar 15–60 cm; a validar), **no** de SoilGrids. Una medición de campo (`root_depth_cm` en el yaml) reemplaza el rango.
- El índice de vegetación detecta «sin plantas verdes», no «suelo desnudo».
- **Memoria honesta:** HLS a 30 m existe desde 2013; MODIS a 250 m, desde 2000. Se dice «décadas de clima y años de observación satelital», no «20 años de su parcela».
- Una fuente sin dato **no se rellena**: el valor sale con `value: null`, y el criterio que dependía de ella se calcula sin ella.

Cada valor que sale de aquí cumple `shared/schema/contract-value.schema.json`.
