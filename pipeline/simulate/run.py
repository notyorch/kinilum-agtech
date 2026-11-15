"""Paso 3 del pipeline: simulador de rotación (plata → oro).  PENDIENTE.

    python -m simulate.run --parcel sin-demo-001

Debe escribir en pipeline/data/gold/<parcela>/simulation.json el bloque `simulation` del paquete
(shared/schema: Simulation), con:

  - E0–E5 × las 49 celdas de `simulate.scenarios.cells()` × 500 o 100 corridas. El garbanzo (E4) y el
    trigo (E5) se calculan con las mismas rutas FAO-56 que el frijol y el sorgo;
  - cada corrida = un año real del historial, con lluvia y temperatura TOMADAS JUNTAS;
  - puntajes enteros 0–100 por criterio (agua, suelo, erosión, clima, ingreso), vía NumPy
    vectorizado, con `simulate.encode.cell_to_json`;
  - reglas de cultivo + FAO-56 desde pipeline/rules/ (`simulate.crops`: versionadas y con fuente), y
    `rules_version` y `generator` para poder repetirlo;
  - el perfil del frijol es el de la variante elegida en la parcela (`simulate.crops.crop_profile`);
  - la bonificación de nitrógeno solo para leguminosas (`simulate.crops.fixes_nitrogen`): sorgo y
    trigo no la reciben;
  - un criterio al que le falta un parámetro del cultivo (`simulate.crops.criteria_without_data`) se
    declara en `simulation.no_data` y sus bytes valen 255: no se inventa;
  - una fuente sin dato NO se rellena: se declara en `provenance` y el criterio que dependía de ella
    se calcula sin ella (degradación elegante).

Hasta que exista, el paquete no lleva `simulation` y la app usa los resultados de ejemplo de
app/src/data/scenarios.ts. NO se generan puntajes de mentira aquí.

Hoy el catálogo (crops.v2) tiene todos los parámetros de cultivo «por definir»: con él, agua, clima
e ingreso de E2–E5 saldrían sin dato. El simulador espera a que el técnico los llene, con fuente.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(__doc__)
    print("simulate.run todavía no está implementado.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
