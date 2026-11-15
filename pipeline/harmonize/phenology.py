"""Calendario del maíz de riego en otoño-invierno: ventana de floración y días de calor dentro de ella.

El calendario es un SUPUESTO del equipo (`rules/maize.v1.yaml`, «a validar con el técnico»): la parcela se siembra a
lo largo del mes declarado y el maíz florece entre 55 y 75 días después. Con `sowing: december`, la ventana va del 25 de
enero al 16 de marzo del año siguiente. Si el técnico da otros días, se cambia el archivo de reglas y nada más.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from functools import lru_cache
from typing import Any

import numpy as np
import yaml

from common.schema import REPO

RULES_PATH = REPO / "pipeline" / "rules" / "maize.v1.yaml"


@lru_cache(maxsize=None)
def maize_rules() -> dict[str, Any]:
    return yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))


def flowering_window(sowing: str, year: int) -> tuple[date, date]:
    """(primer día, último día) de la floración para la siembra declarada, en el año `year`."""
    rules = maize_rules()
    month = rules["meses_de_siembra"].get(sowing)
    if month is None:
        raise ValueError(f"mes de siembra desconocido: {sowing}")
    lo, hi = rules["dias_a_floracion"]
    first, last = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    return first + timedelta(days=lo), last + timedelta(days=hi)


def heat_days_in_window(dates: np.ndarray, tmax: np.ndarray, sowing: str, threshold: float | None = None) -> dict[int, int]:
    """Por año: días de la ventana de floración con temperatura máxima diaria >= umbral. Solo años con la ventana completa."""
    limit = maize_rules()["umbral_calor_c"] if threshold is None else threshold
    out: dict[int, int] = {}
    for year in np.unique(dates.astype("datetime64[Y]").astype(int) + 1970):
        start, end = flowering_window(sowing, int(year))
        in_window = (dates >= np.datetime64(start)) & (dates <= np.datetime64(end))
        expected = (end - start).days + 1
        if in_window.sum() == expected and not np.isnan(tmax[in_window]).any():
            out[int(year)] = int((tmax[in_window] >= limit).sum())
    return out
