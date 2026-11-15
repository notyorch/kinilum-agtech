"""Escenarios y grilla de «¿Qué pasaría si…?» (PRD v0.9). Misma definición que app/src/data/scenarios.ts.

  lluvia:      −30 % … +30 %, de 10 en 10   (7 valores)
  temperatura: −2 … +4 °C, de 1 en 1        (7 valores)
  → 49 celdas. Las 6 que coinciden con un escenario con nombre llevan 500 corridas; las otras, 100.

Seis estrategias: E0 actual · E1 cobertura · E2 frijol regional · E3 sorgo · E4 garbanzo · E5 trigo.
La cuenta de celdas por estrategia no cambia: son las mismas 49.
"""

from __future__ import annotations

from typing import Iterator, NamedTuple

STRATEGIES = ("E0", "E1", "E2", "E3", "E4", "E5")
CRITERIA = ("water", "soil", "erosion", "climate", "income")

# Cultivo del catálogo (pipeline/rules/) que trae cada estrategia. E0 y E1 no traen ninguno.
ROTATION_CROP: dict[str, str] = {"E2": "frijol", "E3": "sorgo", "E4": "garbanzo", "E5": "trigo"}

RAIN_STEPS = (-30, -20, -10, 0, 10, 20, 30)
TEMP_STEPS = (-2, -1, 0, 1, 2, 3, 4)

# Escenario con nombre → (cambio de lluvia en %, cambio de temperatura en °C)
NAMED: dict[str, tuple[int, int]] = {
    "normal": (0, 0),
    "dry": (-10, 0),
    "veryDry": (-20, 0),
    "wet": (10, 0),
    "hot": (0, 2),
    "dryHot": (-10, 2),
}

RUNS_NAMED = 500
RUNS_GRID = 100


class Cell(NamedTuple):
    rain: int
    temp: int
    scenario: str | None
    runs: int


def scenario_at(rain: int, temp: int) -> str | None:
    for name, (r, t) in NAMED.items():
        if (r, t) == (rain, temp):
            return name
    return None


def cells() -> Iterator[Cell]:
    """Las 49 celdas, en el orden de la grilla (lluvia de menor a mayor, y dentro, temperatura)."""
    for rain in RAIN_STEPS:
        for temp in TEMP_STEPS:
            name = scenario_at(rain, temp)
            yield Cell(rain, temp, name, RUNS_NAMED if name else RUNS_GRID)
