"""Temporadas: las partes del oro que no son un valor suelto (lluvia de la temporada, temporadas, normales, umbrales).

Todo sale de datos que ya llegaron (IMERG, POWER, Open-Meteo, NASADEM, HLS); si falta una fuente, la parte no se escribe
y se dice por qué: no se rellena.

  seasons.json   Por temporada de maíz: falta de agua en la FLORACIÓN y días de calor que daña.
                 · falta de agua (mm) = Kc de la etapa media × ET0 − lluvia, sumado en la ventana de floración
                   (`phenology.flowering_window`); con riego, es una medida de cuánta agua tiene que poner el riego.
                 · p10, p50 y p90 = mínimo, mediana y máximo entre las cuatro combinaciones de fuente (lluvia de IMERG
                   u Open-Meteo, ET0 de Open-Meteo o de Penman–Monteith con POWER y viento de 2 m/s): es la dispersión
                   ENTRE FUENTES, no una probabilidad.
                 · `year` es el año de la floración (la siembra de diciembre florece en enero-marzo del año siguiente).
  rain_this_season.json   Lluvia acumulada por mes del último año con datos y lo que se espera después (p10, mediana y p90
                          de lo que llovió en esos meses en los otros años; empírico, no un pronóstico).
  normals.json   Lluvia de mayo a octubre y máximo de mayo, p10–p90 entre años, con su periodo y fuente.
  thresholds.json   Umbrales de una temporada difícil (propuesta, a validar con el técnico): falta de agua por encima del
                    p75 de las temporadas, y el umbral de calor del maíz.
"""

from __future__ import annotations

import calendar
from typing import TYPE_CHECKING, Any

import numpy as np

from ingest.contract import Series
from ingest.eda import et0_pm
from harmonize import phenology
from harmonize.phenology import maize_rules
from harmonize.values import RAIN_MONTHS, month_peaks, season_totals

ET0_U2_DEFAULT = 2.0  # m/s: valor por defecto de FAO-56; el viento de POWER es casi cero en el EDA
DEFICIT_PERCENTILE = 75  # una temporada es difícil si su falta de agua pasa de este percentil de las demás (propuesta)


def _daily(series: Series, column: str, start, end) -> np.ndarray | None:
    """Los valores de `column` en [start, end], o None si falta algún día."""
    days = (end - start).days + 1
    idx = (series.dates >= np.datetime64(start)) & (series.dates <= np.datetime64(end))
    vals = series.col(column)[idx]
    return vals if len(vals) == days and not np.isnan(vals).any() else None


def power_et0(power: Series, lat: float, elev_m: float) -> Series:
    c = power.col
    et0 = et0_pm(power.dates, lat, elev_m, c("T2M"), c("T2M_MAX"), c("T2M_MIN"), c("RH2M"), np.full(len(power), ET0_U2_DEFAULT), c("ALLSKY_SFC_SW_DWN"))
    return Series(power.dates, {"et0": et0})


def flowering_deficits(sowing: str, kc_mid: float, rains: list[tuple[Series, str]], et0s: list[tuple[Series, str]]) -> dict[int, dict[str, float]]:
    """Por año de floración: mínimo, mediana y máximo de la falta de agua entre las combinaciones lluvia × ET0 con la ventana completa."""
    first = min(int(s.dates[0].astype("datetime64[Y]").astype(int)) + 1970 for s, _ in rains + et0s)
    last = max(int(s.dates[-1].astype("datetime64[Y]").astype(int)) + 1970 for s, _ in rains + et0s)
    out: dict[int, dict[str, float]] = {}
    for sow_year in range(first, last + 1):
        start, end = phenology.flowering_window(sowing, sow_year)
        totals = []
        for rs, rc in rains:
            rain = _daily(rs, rc, start, end)
            for es, ec in et0s:
                et0 = _daily(es, ec, start, end)
                if rain is not None and et0 is not None:
                    totals.append(max(0.0, float(kc_mid * et0.sum() - rain.sum())))
        if len(totals) == len(rains) * len(et0s):
            out[end.year] = {"p10": min(totals), "p50": float(np.median(totals)), "p90": max(totals)}
    return out


def seasons_part(sowing: str, kc_mid: float, rains, et0s, power: Series) -> list[dict[str, Any]]:
    deficits = flowering_deficits(sowing, kc_mid, rains, et0s)
    heat = {phenology.flowering_window(sowing, y)[1].year: n for y, n in phenology.heat_days_in_window(power.dates, power.col("T2M_MAX"), sowing).items()}
    return [{"year": y, "deficit": {k: round(v, 1) for k, v in d.items()}, "heat_days": heat[y]} for y, d in sorted(deficits.items()) if y in heat]


def rain_this_season_part(imerg: Series) -> dict[str, Any] | None:
    """Acumulado por mes (enero a diciembre) del último año con datos y la banda de lo que sigue; None si no hay meses completos."""
    col = imerg.col("precip_mm_day")
    years = imerg.dates.astype("datetime64[Y]").astype(int) + 1970
    months = imerg.dates.astype("datetime64[M]").astype(int) % 12 + 1

    def monthly_cum(year: int) -> list[float]:
        cum, out = 0.0, []
        for m in range(1, 13):
            w = (years == year) & (months == m)
            if w.sum() != calendar.monthrange(year, m)[1] or np.isnan(col[w]).any():
                break
            cum += float(col[w].sum())
            out.append(cum)
        return out

    last = int(years.max())
    observed = monthly_cum(last)
    if not observed:
        return None
    n = len(observed)
    full = [c for y in sorted({int(v) for v in years}) if y != last and len(c := monthly_cum(y)) == 12]
    projected = []
    if n < 12 and len(full) >= 3:
        for m in range(n, 12):
            inc = np.array([c[m] - c[n - 1] for c in full])
            projected.append({"y": round(observed[-1] + float(np.median(inc)), 1), "lo": round(observed[-1] + float(np.percentile(inc, 10)), 1), "hi": round(observed[-1] + float(np.percentile(inc, 90)), 1)})
    return {"observed": [round(v, 1) for v in observed], "projected": projected}


def normals_part(imerg: Series, power: Series) -> dict[str, Any]:
    out: dict[str, Any] = {"_nota": "Lo normal en la zona: rango p10–p90 entre los años con datos, para decir si un dato es mucho o poco. Calculado de las series de IMERG y POWER."}
    totals = season_totals(imerg.dates, imerg.col("precip_mm_day"), RAIN_MONTHS)
    if len(totals) >= 3:
        ys = sorted(totals)
        v = np.array(list(totals.values()))
        out["rain"] = {"p10": round(float(np.percentile(v, 10)), 0), "p90": round(float(np.percentile(v, 90)), 0), "unit": "mm", "period": f"{ys[0]}–{ys[-1]}", "source": "GPM IMERG"}
    peaks = month_peaks(power.dates, power.col("T2M_MAX"), 5)
    if len(peaks) >= 3:
        ys = sorted(peaks)
        v = np.array(list(peaks.values()))
        out["heat"] = {"p10": round(float(np.percentile(v, 10)), 1), "p90": round(float(np.percentile(v, 90)), 1), "unit": "°C", "period": f"{ys[0]}–{ys[-1]}", "source": "NASA POWER"}
    return out


def thresholds_part(seasons: list[dict[str, Any]]) -> dict[str, float] | None:
    if len(seasons) < 3:
        return None
    return {"deficit_mm": round(float(np.percentile([s["deficit"]["p50"] for s in seasons], DEFICIT_PERCENTILE)), 0), "heat_c": float(maize_rules()["umbral_calor_c"])}


def gold_parts(results: dict[str, Any], config: dict[str, Any], lat: float, lon: float) -> tuple[dict[str, Any], list[str]]:
    """Las partes del oro que se pueden armar con lo que llegó, y por qué no se armó cada una de las demás."""
    from simulate.crops import load_catalog

    parts: dict[str, Any] = {}
    why: list[str] = []
    fetched = {k: r.fetch.data for k, r in results.items() if getattr(r, "fetch", None) is not None and isinstance(r.fetch.data, Series)}
    need = [k for k in ("imerg", "power", "openmeteo") if k not in fetched]
    if need:
        return parts, [f"sin {', '.join(need)}: no se arman las temporadas ni los normales"]
    imerg, power, om = fetched["imerg"], fetched["power"], fetched["openmeteo"]
    nasadem = results.get("nasadem")
    elev = float(nasadem.fetch.data["elevation_m"]["point"]) if nasadem is not None and nasadem.fetch is not None and nasadem.fetch.data["elevation_m"].get("point") is not None else None
    if elev is None:
        why.append("sin la elevación de NASADEM: la ET0 de POWER no se calcula, así que no hay temporadas")
    else:
        kc_mid = load_catalog()["maiz_base"]["kc_por_etapa"]["media"]
        seasons = seasons_part(config["sowing"], kc_mid, [(imerg, "precip_mm_day"), (om, "precipitation_sum")], [(om, "et0_fao_evapotranspiration"), (power_et0(power, lat, elev), "et0")], power)
        if seasons:
            parts["seasons.json"] = seasons
            th = thresholds_part(seasons)
            if th:
                parts["thresholds.json"] = th
        else:
            why.append("ninguna temporada tiene completa la ventana de floración en todas las fuentes")
    rain = rain_this_season_part(imerg)
    if rain:
        parts["rain_this_season.json"] = rain
    normals = normals_part(imerg, power)
    if len(normals) > 1:
        parts["normals.json"] = normals
    cover = results.get("hls_ndvi")
    if cover is not None and cover.fetch is not None and cover.fetch.data:
        parts["meta.json"] = {"clean_pixels": int(max(o.n_cells for o in cover.fetch.data))}
    else:
        why.append("sin los píxeles de HLS: no se sabe cuántos cuadros limpios hay (meta.json)")
    return parts, why
