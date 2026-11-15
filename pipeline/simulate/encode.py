"""Codificación de los puntajes del paquete (shared/schema: SimulationCell.scores).

Cada celda guarda bytes sin signo en base64, con la disposición [estrategia][criterio][corrida]
(orden de `STRATEGIES` y `CRITERIA`). Cada byte es un puntaje entero 0–100. La corrida i es el
MISMO año simulado para las seis estrategias y los cinco criterios: así el motor puede contar
cuántas veces queda primera cada una.

Un criterio sin dato (al cultivo le falta un parámetro) NO se rellena: se declara en
`simulation.no_data` y sus bytes valen `NO_DATA` (255) en todas las corridas.
"""

from __future__ import annotations

import base64
from typing import Mapping, Sequence

import numpy as np

from .scenarios import CRITERIA, STRATEGIES, Cell

NO_DATA = 255
NoData = Mapping[str, Sequence[str]]


def _mask(no_data: NoData | None) -> np.ndarray:
    """Matriz (estrategias, criterios): True donde el criterio está declarado sin dato."""
    mask = np.zeros((len(STRATEGIES), len(CRITERIA)), dtype=bool)
    for strategy, criteria in (no_data or {}).items():
        for criterion in criteria:
            mask[STRATEGIES.index(strategy), CRITERIA.index(criterion)] = True
    return mask


def encode_scores(scores: np.ndarray, no_data: NoData | None = None) -> str:
    """`scores` con forma (6, 5, corridas) y valores 0–100 → texto base64.

    Los criterios de `no_data` se escriben como 255, traigan lo que traigan (lo normal es NaN).
    Un NaN que no esté declarado es un error: una fuente sin dato se declara, no se rellena.
    """
    arr = np.asarray(scores, dtype=float)
    if arr.ndim != 3 or arr.shape[:2] != (len(STRATEGIES), len(CRITERIA)):
        raise ValueError(f"los puntajes deben tener forma ({len(STRATEGIES)}, {len(CRITERIA)}, corridas), no {arr.shape}")
    mask = _mask(no_data)
    known = arr[~mask]
    if not np.all(np.isfinite(known)):
        raise ValueError("hay puntajes que no son números (¿un criterio sin dato? declárelo en no_data, no lo rellene)")
    rounded = np.rint(np.where(mask[:, :, None], NO_DATA, arr))
    if known.size and (np.rint(known).min() < 0 or np.rint(known).max() > 100):
        raise ValueError("los puntajes deben estar entre 0 y 100")
    return base64.b64encode(rounded.astype(np.uint8).tobytes(order="C")).decode("ascii")


def decode_scores(text: str, runs: int) -> np.ndarray:
    """Lo contrario de `encode_scores`: devuelve un arreglo (6, 5, corridas) de enteros (255 = sin dato)."""
    raw = base64.b64decode(text, validate=True)
    expected = len(STRATEGIES) * len(CRITERIA) * runs
    if len(raw) != expected:
        raise ValueError(f"scores mide {len(raw)} bytes y debe medir {expected}")
    return np.frombuffer(raw, dtype=np.uint8).reshape(len(STRATEGIES), len(CRITERIA), runs)


def cell_to_json(cell: Cell, scores: np.ndarray, no_data: NoData | None = None) -> dict:
    """Una celda lista para `simulation.cells` del paquete."""
    if scores.shape[2] != cell.runs:
        raise ValueError(f"la celda {cell.rain}/{cell.temp} pide {cell.runs} corridas y trae {scores.shape[2]}")
    out: dict = {"rain": cell.rain, "temp": cell.temp, "runs": cell.runs, "scores": encode_scores(scores, no_data)}
    if cell.scenario:
        out = {"scenario": cell.scenario, **out}
    return out
