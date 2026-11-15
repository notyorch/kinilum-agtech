"""El modelo del simulador, en funciones puras (sin red ni archivos).

Agua (v1): lo que el riego tiene que poner en un ciclo = evapotranspiración del cultivo (ETc) − lluvia del ciclo, en mm.
  ETc = suma diaria de Kc × ET0, con la curva de Kc de FAO-56 (inicial, desarrollo, media y final).
  No hay reserva de agua en el suelo ni pérdidas de riego: es la necesidad del cultivo, no el agua que se aplica.
Ciclo del maíz: grados día acumulados desde la siembra hasta la cosecha (INIFAP, Tabla 20), con base 10 °C y tope 30 °C
  (supuesto del equipo: la tabla no dice con qué base se calcularon). Con más calor el ciclo se acorta.
"""

from __future__ import annotations

import numpy as np

GDD_BASE_C = 10.0
GDD_CAP_C = 30.0


def kc_curve(cycle_days: int, stage_days: tuple[float, float, float, float] | list[float], kc: dict[str, float]) -> np.ndarray:
    """Kc de cada día del ciclo. Las etapas (inicial, desarrollo, media, final) se escalan para sumar `cycle_days`.

    Inicial y media son constantes; el desarrollo sube lineal de Kc inicial a Kc media y la etapa final baja lineal a Kc final.
    """
    if cycle_days < 1:
        return np.zeros(0)
    total = float(sum(stage_days))
    ini, dev, mid, _late = (cycle_days * s / total for s in stage_days)
    x = np.array([0.0, ini, ini + dev, ini + dev + mid, float(cycle_days)])
    y = np.array([kc["inicial"], kc["inicial"], kc["media"], kc["media"], kc["final"]])
    return np.interp(np.arange(cycle_days) + 0.5, x, y)


def crop_need(et0: np.ndarray, rain: np.ndarray, start: int, cycle_days: int, kc: dict[str, float], stage_days) -> dict[str, float]:
    """ETc, lluvia y necesidad de riego (mm) de un ciclo que empieza el día `start` de la serie.

    Si la serie se acaba antes que el ciclo, el ciclo se corta ahí y se anota en `cut`.
    """
    end = min(start + cycle_days, len(et0))
    days = end - start
    curve = kc_curve(cycle_days, stage_days, kc)[:days]
    etc = float(np.sum(curve * et0[start:end]))
    rainfall = float(np.sum(rain[start:end]))
    return {"etc": etc, "rain": rainfall, "need": max(0.0, etc - rainfall), "days": days, "cut": days < cycle_days}


def gdd_cycle_days(tmean: np.ndarray, start: int, target_gdd: float, base: float = GDD_BASE_C, cap: float = GDD_CAP_C) -> int:
    """Días desde la siembra hasta acumular `target_gdd` grados día. Si la serie no alcanza, devuelve los días que hay."""
    daily = np.clip(np.minimum(tmean[start:], cap) - base, 0.0, None)
    cumulative = np.cumsum(daily)
    hit = np.searchsorted(cumulative, target_gdd)
    return int(min(hit + 1, len(daily)))


def window_offset(day_month: str, season_start_month: int = 10) -> int:
    """Día del año agrícola (el 1 de octubre es el 0) de una fecha «25-oct». Año de referencia no bisiesto."""
    months = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
    from datetime import date

    day, mon = day_month.split("-")
    m = months[mon]
    year = 2001 if m >= season_start_month else 2002
    return (date(year, m, int(day)) - date(2001, season_start_month, 1)).days


def need_score(need: np.ndarray, ceiling: float) -> np.ndarray:
    """Puntaje de agua 0–100: 100 = no pide riego; 0 = pide `ceiling` mm o más."""
    return np.clip(100.0 * (1.0 - need / ceiling), 0.0, 100.0)


def income_score(revenue: np.ndarray, ceiling: float) -> np.ndarray:
    """Puntaje de ingreso 0–100: 100 = el ingreso bruto de `ceiling` pesos por hectárea o más."""
    return np.clip(100.0 * revenue / ceiling, 0.0, 100.0)
