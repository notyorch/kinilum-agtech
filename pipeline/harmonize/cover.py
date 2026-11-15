"""Plantas verdes: del NDVI de cada escena a la clase de cada mes y a los días sin plantas verdes de cada año.

Cada mes se clasifica con la MEDIANA del NDVI de sus escenas despejadas sobre la parcela:

  C  con plantas verdes   (NDVI ≥ 0.35)
  B  sin plantas verdes   (NDVI < 0.35)
  N  sin dato             (ninguna escena despejada ese mes)

Los meses N NO cuentan como «sin plantas verdes»: no se sabe qué pasó. Por eso `days_without_green_cover` es un MÍNIMO
(«al menos»), y un año solo cuenta si tiene al menos 9 meses con dato. El umbral de 0.35 es una propuesta del documento 02
y se calibra con un técnico local. El NDVI detecta plantas verdes, no «suelo desnudo».
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from typing import Any

import numpy as np

from ingest.contract import Fetch, contract_value
from ingest.vegetation import Observation

GREEN_NDVI_MIN = 0.35  # propuesta, a calibrar con un técnico local
MIN_KNOWN_MONTHS = 9  # meses con dato para que un año cuente
MIN_YEARS = 3
CODE = "C = con plantas verdes · B = sin plantas verdes · N = sin dato (ninguna escena despejada)"


def monthly_classes(observations: list[Observation], first_year: int, last_year: int, threshold: float = GREEN_NDVI_MIN) -> dict[int, str]:
    """Una cadena de 12 letras (C, B o N) por año, de enero a diciembre."""
    by_month: dict[tuple[int, int], list[float]] = defaultdict(list)
    for o in observations:
        if np.isfinite(o.ndvi):
            by_month[(o.date.year, o.date.month)].append(o.ndvi)
    out: dict[int, str] = {}
    for year in range(first_year, last_year + 1):
        letters = []
        for month in range(1, 13):
            vals = by_month.get((year, month))
            letters.append("N" if not vals else "C" if float(np.median(vals)) >= threshold else "B")
        out[year] = "".join(letters)
    return out


def bare_days(classes: dict[int, str]) -> dict[int, int]:
    """Por año con al menos 9 meses con dato: los días de los meses B. Un MÍNIMO: los meses N no se cuentan."""
    out: dict[int, int] = {}
    for year, letters in classes.items():
        if 12 - letters.count("N") >= MIN_KNOWN_MONTHS:
            out[year] = sum(calendar.monthrange(year, m)[1] for m, ch in enumerate(letters, 1) if ch == "B")
    return out


def green_cover_json(fetch: Fetch) -> dict[str, Any]:
    """La parte `green_cover` del oro: la clase de cada mes de cada año."""
    p = fetch.prov.params
    classes = monthly_classes(fetch.data, int(p["start"][:4]), int(p["end"][:4]))
    return {"_codigo": CODE, "source": f"HLS v2.0, NDVI ≥ {GREEN_NDVI_MIN} (propuesta, a calibrar); Sentinel-2 como respaldo", "years": {str(y): s for y, s in classes.items()}}


def bare_value(fetch: Fetch) -> dict[str, Any]:
    """`days_without_green_cover`: días al año sin plantas verdes, como MÍNIMO. Mediana y rango entre años."""
    p = fetch.prov.params
    observations: list[Observation] = fetch.data
    classes = monthly_classes(observations, int(p["start"][:4]), int(p["end"][:4]))
    days = bare_days(classes)
    clear = [o for o in observations if np.isfinite(o.ndvi)]
    common = dict(unit="days", prov=fetch.prov, native_resolution="30 m", native_res_m=30, method="measured", assumptions=["innerBuffer", "greenNotStubble"])
    if len(days) < MIN_YEARS or not clear:
        return contract_value("days_without_green_cover", None, None, None, timestamp="2025", extra_steps=[f"sin dato: {len(days)} años con al menos {MIN_KNOWN_MONTHS} meses con dato y se necesitan {MIN_YEARS}"], **common)
    vals = np.array(list(days.values()), dtype=float)
    years = sorted(days)
    n_s2 = sum(1 for o in clear if o.sensor == "S2")
    steps = [
        "HLSL30 v2.0, HLSS30 v2.0", "mask: Fmask (nube, sombra, cirro, nieve, agua)", "buffer: -30 m",
        f"NDVI < {GREEN_NDVI_MIN} = sin plantas verdes (propuesta, a calibrar con el técnico)",
        "mes sin escena despejada: no cuenta como sin plantas verdes, así que es un mínimo",
        f"p10, mediana y p90 entre {len(years)} años con al menos {MIN_KNOWN_MONTHS} meses con dato ({years[0]}–{years[-1]})",
        f"{len(clear) - n_s2} observaciones de HLS" + (f" y {n_s2} de Sentinel-2 (respaldo)" if n_s2 else ""),
    ]
    last = max(o.date for o in clear)
    return contract_value("days_without_green_cover", float(np.median(vals)), float(np.percentile(vals, 10)), float(np.percentile(vals, 90)), timestamp=f"{last.year}-{last.month:02d}", extra_steps=steps, **common)
