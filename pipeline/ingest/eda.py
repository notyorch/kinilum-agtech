"""EDA: mirar los datos antes de usarlos. Cada función responde una pregunta y no inventa nada.

Solo NumPy. Las etapas siguen el documento 02 (E0 a E8): estado, cobertura, calidad, estacionalidad,
consistencia entre fuentes de lluvia, soporte, balance de agua, y plan de degradación. Todo umbral es una
PROPUESTA que se calibra con un técnico local.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Any

import numpy as np

from .catalog import BY_ID, CORE, rows
from .contract import STATUS_OK, Series, clean_pixels
from .load import Params, Result

# Límites físicos: atrapan errores de captura, no clima extremo.
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "PRECTOTCORR": (0, 600), "T2M": (-10, 50), "T2M_MAX": (-10, 55), "T2M_MIN": (-10, 50), "RH2M": (0, 100),
    "WS2M": (0, 60), "ALLSKY_SFC_SW_DWN": (0, 45),
    "precipitation_sum": (0, 600), "precip_mm_day": (0, 600), "neighbor_mm_day": (0, 600), "et0_fao_evapotranspiration": (0, 15), "temperature_2m_max": (-10, 55),
    "temperature_2m_min": (-10, 50), "shortwave_radiation_sum": (0, 45),
}
# Mediana esperada de una variable en tierra abierta. Fuera de ese rango no es un error de captura, pero el
# dato no sirve para lo que se quiere (propuesta).
TYPICAL_MEDIAN: dict[str, tuple[float, float, str]] = {
    "WS2M": (0.5, 12.0, "viento a 2 m en m/s: casi nunca es tan bajo; la ET0 de FAO-56 subestima el término aerodinámico"),
}

WET_MM = 1.0            # día lluvioso (propuesta)
CLOUD_MAX = 30          # % de nubes aceptado en una escena (propuesta)
RAIN_BIAS_WARN = 25.0   # % de sesgo entre fuentes de lluvia (propuesta)
ET0_DIFF_WARN = 20.0    # % de diferencia de ET0 con Open-Meteo (propuesta)
FAO56_DEFAULT_U2 = 2.0  # m/s: valor que FAO-56 propone cuando no hay viento medido
EDGE_WARN_DEG = 0.02    # a menos de ~2 km del borde de la celda de IMERG, la vecina podría dar otro resultado


def longest_run(flags: np.ndarray) -> int:
    best = cur = 0
    for f in flags:
        cur = cur + 1 if f else 0
        best = max(best, cur)
    return best


def corr(x: np.ndarray, y: np.ndarray) -> float | None:
    """Correlación de Pearson, o None si no se puede calcular (poco dato o una serie constante)."""
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return round(float(np.corrcoef(x, y)[0, 1]), 3)


def monthly(dates: np.ndarray, values: np.ndarray, how: str = "sum") -> tuple[np.ndarray, np.ndarray]:
    """Totales (o medias) por mes, solo de meses completos. Devuelve (meses datetime64[M], valores)."""
    ok = ~np.isnan(values)
    months = dates.astype("datetime64[M]")
    uniq, inv = np.unique(months, return_inverse=True)
    n_obs = np.bincount(inv, weights=ok.astype(float), minlength=len(uniq))
    total = np.bincount(inv, weights=np.where(ok, values, 0.0), minlength=len(uniq))
    n_days = ((uniq + np.timedelta64(1, "M")).astype("datetime64[D]") - uniq.astype("datetime64[D]")).astype(int)
    full = n_obs == n_days
    out = total if how == "sum" else total / np.maximum(n_obs, 1)
    return uniq[full], out[full]


def monthly_percentiles(dates: np.ndarray, values: np.ndarray, how: str = "sum") -> dict[int, dict[str, float]]:
    """p10, mediana y p90 entre años de cada mes del calendario."""
    months, vals = monthly(dates, values, how)
    cal = months.astype(int) % 12 + 1
    out = {}
    for m in range(1, 13):
        v = vals[cal == m]
        if len(v):
            out[m] = {"p10": float(np.percentile(v, 10)), "p50": float(np.median(v)), "p90": float(np.percentile(v, 90)), "anios": int(len(v))}
    return out


def coverage(series: Series) -> dict[str, dict[str, Any]]:
    """Días con dato, cobertura y hueco más largo de cada variable, sobre la malla diaria completa."""
    first, last = series.dates[0], series.dates[-1]
    grid = np.arange(first, last + np.timedelta64(1, "D"), dtype="datetime64[D]")
    out = {}
    for name, col in series.columns.items():
        present = np.isin(grid, series.dates[~np.isnan(col)])
        out[name] = {
            "dias_esperados": int(len(grid)), "dias_con_dato": int(present.sum()),
            "cobertura_pct": round(100 * float(present.mean()), 2), "hueco_mas_largo_dias": longest_run(~present),
            "primer_dia": str(series.dates[~np.isnan(col)][0]) if (~np.isnan(col)).any() else None,
        }
    return out


def quality(series: Series) -> dict[str, dict[str, Any]]:
    """Faltantes, duplicados, valores fuera de rango físico y medianas que no tienen sentido."""
    out: dict[str, dict[str, Any]] = {"_duplicados_indice": {"n": int(len(series.dates) - len(np.unique(series.dates)))}}
    for name, col in series.columns.items():
        ok = col[~np.isnan(col)]
        lo, hi = PHYSICAL_BOUNDS.get(name, (-math.inf, math.inf))
        row: dict[str, Any] = {"faltantes_pct": round(100 * float(np.isnan(col).mean()), 2),
                               "fuera_de_rango": int(((ok < lo) | (ok > hi)).sum()) if len(ok) else 0}
        if len(ok):
            row.update(min=round(float(ok.min()), 2), mediana=round(float(np.median(ok)), 2), max=round(float(ok.max()), 2))
            if name in TYPICAL_MEDIAN:
                tlo, thi, why = TYPICAL_MEDIAN[name]
                if not tlo <= float(np.median(ok)) <= thi:
                    row["mediana_inverosimil"] = why
        out[name] = row
    return out


def rain_agreement(a: Series, a_col: str, b: Series, b_col: str, wet_mm: float = WET_MM) -> dict[str, Any]:
    """¿Coinciden dos series de lluvia? Correlación mensual, sesgo total y acuerdo día lluvioso / seco."""
    common, ia, ib = np.intersect1d(a.dates, b.dates, return_indices=True)
    x, y = a.col(a_col)[ia], b.col(b_col)[ib]
    ok = ~np.isnan(x) & ~np.isnan(y)
    dates, x, y = common[ok], x[ok], y[ok]
    if len(dates) < 30:
        return {"dias_comunes": int(len(dates)), "nota": "muy pocos días en común"}
    _, mx = monthly(dates, x)
    _, my = monthly(dates, y)
    ax, ay = annual_totals(dates, x), annual_totals(dates, y)
    return {
        "dias_comunes": int(len(dates)),
        "corr_mensual": corr(mx, my),
        # Positivo: la PRIMERA serie llueve más que la segunda. (El notebook medía al revés: segunda − primera.)
        "sesgo_pct_total": round(100 * float((x.sum() - y.sum()) / y.sum()), 1) if y.sum() > 0 else None,
        "definicion_sesgo": "(primera − segunda) / segunda",
        "anual_mediana_mm_primera": round(float(np.median(ax))) if len(ax) else None,
        "anual_mediana_mm_segunda": round(float(np.median(ay))) if len(ay) else None,
        "acuerdo_lluvioso_seco_pct": round(100 * float(np.mean((x >= wet_mm) == (y >= wet_mm))), 1),
        "umbral_dia_lluvioso_mm": wet_mm,
    }


def es_kpa(t: np.ndarray) -> np.ndarray:
    return 0.6108 * np.exp(17.27 * t / (t + 237.3))


def et0_pm(dates: np.ndarray, lat: float, elev_m: float, t: np.ndarray, tmax: np.ndarray, tmin: np.ndarray,
           rh: np.ndarray, u2: np.ndarray, rs_mj: np.ndarray) -> np.ndarray:
    """ET0 diaria de FAO-56 Penman–Monteith (mm/día). G = 0, albedo 0.23, ea con HR media y T media."""
    doy = (dates - dates.astype("datetime64[Y]")).astype(int) + 1
    ea = rh / 100 * es_kpa(t)
    es = (es_kpa(tmax) + es_kpa(tmin)) / 2
    delta = 4098 * es_kpa(t) / (t + 237.3) ** 2
    gamma = 0.000665 * 101.3 * ((293 - 0.0065 * elev_m) / 293) ** 5.26
    phi = math.radians(lat)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    ra = (24 * 60 / np.pi) * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    rso = (0.75 + 2e-5 * elev_m) * ra
    ratio = np.clip(rs_mj / np.where(rso > 0, rso, np.nan), 0.3, 1.0)
    rnl = 4.903e-9 * (((tmax + 273.16) ** 4 + (tmin + 273.16) ** 4) / 2) * (0.34 - 0.14 * np.sqrt(ea)) * (1.35 * ratio - 0.35)
    rn = 0.77 * rs_mj - rnl
    et0 = (0.408 * delta * rn + gamma * 900 / (t + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    return np.clip(et0, 0, None)


def annual_totals(dates: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Total por año, solo de años completos."""
    ok = ~np.isnan(values)
    years = dates.astype("datetime64[Y]")
    uniq, inv = np.unique(years, return_inverse=True)
    n = np.bincount(inv, weights=ok.astype(float), minlength=len(uniq))
    tot = np.bincount(inv, weights=np.where(ok, values, 0.0), minlength=len(uniq))
    days = ((uniq + np.timedelta64(1, "Y")).astype("datetime64[D]") - uniq.astype("datetime64[D]")).astype(int)
    return tot[n == days]


def dry_spells(dates: np.ndarray, rain: np.ndarray, wet_mm: float = WET_MM) -> dict[str, float]:
    """Racha seca más larga de cada año (días seguidos con menos de `wet_mm`), p10, mediana y p90."""
    years = dates.astype("datetime64[Y]")
    spells = [longest_run(rain[years == y] < wet_mm) for y in np.unique(years)]
    return {"p10": float(np.percentile(spells, 10)), "p50": float(np.median(spells)), "p90": float(np.percentile(spells, 90))}


def scene_summary(scenes: list[dict[str, Any]], start: str, end: str, cloud_max: float = CLOUD_MAX) -> dict[str, Any]:
    clouds = np.array([s["cloud"] for s in scenes if s["cloud"] is not None], dtype=float)
    clean = [s for s in scenes if s["cloud"] is not None and s["cloud"] <= cloud_max]
    all_months = np.arange(np.datetime64(start[:7], "M"), np.datetime64(end[:7], "M") + np.timedelta64(1, "M"))
    have = {s["datetime"].strftime("%Y-%m") for s in clean}
    any_scene = {s["datetime"].strftime("%Y-%m") for s in scenes}
    by_cal = {m: sum(1 for s in clean if s["datetime"].month == m) for m in range(1, 13)}
    return {
        "escenas": len(scenes), "escenas_limpias": len(clean), "cloud_max_pct": cloud_max,
        "primera_escena": str(min(s["datetime"] for s in scenes).date()) if scenes else None,
        "nubes_p50": float(np.median(clouds)) if len(clouds) else None, "nubes_p90": float(np.percentile(clouds, 90)) if len(clouds) else None,
        "meses_en_el_periodo": int(len(all_months)), "meses_sin_escena_limpia": [str(m) for m in all_months if str(m) not in have],
        # Sin ninguna escena (el producto no existía o no cubre) no es lo mismo que «solo hubo nubes».
        "meses_sin_ninguna_escena": [str(m) for m in all_months if str(m) not in any_scene],
        "meses_solo_con_nubes": [str(m) for m in all_months if str(m) in any_scene and str(m) not in have],
        "escenas_limpias_por_mes_del_anio": by_cal,
    }


def degradation_plan(results: dict[str, Result]) -> tuple[list[dict[str, str]], bool]:
    """«Nada simulado» aplicado fuente por fuente. Devuelve (decisiones, ¿detener la entrega?)."""
    ok = lambda s: s in results and results[s].status == STATUS_OK  # noqa: E731
    plan: list[tuple[str, str, str]] = []
    stop = False
    if not ok("grace"):
        plan.append(("grace", "omitir; nada visible cambia", "ninguno"))
    if not ok("smap"):
        plan.append(("smap", "humedad de contexto desde el balance de agua con POWER y GPM", "Humedad estimada"))
    if not ok("ecostress"):
        plan.append(("ecostress", "calor desde POWER", "Evidencia de parcela no disponible"))
    if not ok("modis"):
        plan.append(("modis", "usar VIIRS si está en el catálogo; si no, marcar por integrar", "según el caso"))
    if not ok("hls_stac"):
        if ok("modis") or ok("s2_earthsearch"):
            plan.append(("hls_stac", "bajar el soporte a entorno con MODIS o Sentinel-2", "Entorno"))
        else:
            plan.append(("hls_stac", "SIN RESPALDO: detener la entrega", "—"))
            stop = True
    for core in ("power", "nasadem"):
        if not ok(core):
            plan.append((core, "SIN RESPALDO: detener la entrega", "—"))
            stop = True
    if not ok("imerg"):
        if ok("openmeteo"):
            plan.append(("imerg", "hay contraste (Open-Meteo): el equipo decide si lo sustituye; mientras tanto no se publica como fuente de zona", "Lluvia de zona no disponible"))
        else:
            plan.append(("imerg", "SIN RESPALDO: detener la entrega", "—"))
            stop = True
    return [{"fuente": f, "accion": a, "aviso_en_pantalla": v} for f, a, v in plan], stop


def build_report(results: dict[str, Result], params: Params, *, elev_m: float = 40.0, cloud_max: float = CLOUD_MAX, wet_mm: float = WET_MM) -> dict[str, Any]:
    """Informe completo. Una etapa que no tiene sus datos se declara «por integrar»; nunca se inventa."""
    warnings: list[str] = []
    data = lambda sid: results[sid].fetch.data if sid in results and results[sid].fetch else None  # noqa: E731
    power, om, im, nd = data("power"), data("openmeteo"), data("imerg"), data("nasadem")
    stages: dict[str, Any] = {}

    stages["E0"] = {"titulo": "Estado de las fuentes", "fuentes": {k: {"estado": r.status, "detalle": r.detail} for k, r in results.items()}}

    cov: dict[str, Any] = {}
    for sid, series in (("power", power), ("openmeteo", om), ("imerg", im)):
        if series is not None:
            cov.update({f"{sid}.{k}": v for k, v in coverage(series).items()})
    for sid in ("hls_stac", "s2_earthsearch"):
        if data(sid) is not None:
            cov[sid] = scene_summary(data(sid), params.start, params.end, cloud_max)
    stages["E1"] = {"titulo": "Cobertura temporal y huecos", "cobertura": cov}

    qual: dict[str, Any] = {}
    for sid, series in (("power", power), ("openmeteo", om), ("imerg", im)):
        if series is not None:
            qual[sid] = quality(series)
            for name, row in qual[sid].items():
                if isinstance(row, dict) and "mediana_inverosimil" in row:
                    warnings.append(f"{sid}.{name}: mediana de {row['mediana']} inverosímil ({row['mediana_inverosimil']})")
    if "soilgrids" in results and results["soilgrids"].status != STATUS_OK:
        warnings.append(f"SoilGrids sin dato en este punto: {results['soilgrids'].detail}")
    stages["E2"] = {"titulo": "Calidad de los datos", "calidad": qual}

    e3: dict[str, Any] = {"titulo": "Estacionalidad"}
    if power is not None:
        rain_m = monthly_percentiles(power.dates, power.col("PRECTOTCORR"), "sum")
        tmax_m = monthly_percentiles(power.dates, power.col("T2M_MAX"), "mean")
        annual = annual_totals(power.dates, power.col("PRECTOTCORR"))
        e3.update(
            lluvia_mensual_mm=rain_m, tmax_mensual_c=tmax_m,
            meses_mas_lluviosos=[m for m, _ in sorted(rain_m.items(), key=lambda kv: -kv[1]["p50"])[:5]],
            lluvia_anual_suma_de_medianas_mm=round(sum(v["p50"] for v in rain_m.values())),
            lluvia_anual_mediana_entre_anios_mm=round(float(np.median(annual))) if len(annual) else None,
        )
    else:
        e3["estado"] = "por integrar: POWER no llegó"
    if im is not None:
        im_annual = annual_totals(im.dates, im.col("precip_mm_day"))
        e3["imerg"] = {
            "lluvia_mensual_mm": monthly_percentiles(im.dates, im.col("precip_mm_day"), "sum"),
            "lluvia_anual_mediana_entre_anios_mm": round(float(np.median(im_annual))) if len(im_annual) else None,
            "anios_completos": int(len(im_annual)),
        }
    stages["E3"] = e3

    sources = {"POWER": (power, "PRECTOTCORR"), "Open-Meteo": (om, "precipitation_sum"), "IMERG": (im, "precip_mm_day")}
    have = [n for n, (s_, _) in sources.items() if s_ is not None]
    pairs: dict[str, Any] = {}
    for x, y in combinations(have, 2):
        pairs[f"{x} vs {y}"] = rain_agreement(sources[x][0], sources[x][1], sources[y][0], sources[y][1], wet_mm)
    if im is not None:
        pairs["IMERG celda vs vecina"] = rain_agreement(im, "precip_mm_day", im, "neighbor_mm_day", wet_mm)
    if pairs:
        stages["E4"] = {"titulo": "Consistencia entre fuentes de lluvia", "pares": pairs}
        for name, pair in pairs.items():
            if abs(pair.get("sesgo_pct_total") or 0) > RAIN_BIAS_WARN:
                warnings.append(f"Sesgo de lluvia de {pair['sesgo_pct_total']} % en {name} (> {RAIN_BIAS_WARN:g} %): revisar antes de usar ambas")
        cell = (results["imerg"].fetch.prov.params.get("cell") or {}) if im is not None else {}
        if cell.get("margin_deg") is not None and cell["margin_deg"] < EDGE_WARN_DEG:
            near = pairs["IMERG celda vs vecina"].get("sesgo_pct_total")
            warnings.append(f"IMERG: el punto está a {cell['margin_deg']}° del borde de su celda; la celda vecina da {near} % de diferencia en la lluvia total")
    else:
        stages["E4"] = {"titulo": "Consistencia entre fuentes de lluvia", "estado": "por integrar: hacen falta al menos dos fuentes de lluvia"}

    supp = []
    for s in rows():
        res = results.get(s["id"])
        px = clean_pixels(params.plot_side_m, s["native_res_m"])
        supp.append({"id": s["id"], "res_nativa_m": s["native_res_m"], "soporte": s["support"], "estado": res.status if res else "no pedida",
                     "pixeles_limpios_en_parcela": px, "soporte_efectivo": s["support"] if res and res.status == STATUS_OK else "sin_dato"})
    stages["E5"] = {"titulo": "Nivel de soporte y píxeles limpios", "plot_side_m": params.plot_side_m, "fuentes": supp}

    elev_src = "supuesto, parámetro del informe"
    if nd is not None and nd["elevation_m"]["point"] is not None:
        elev_m, elev_src = float(nd["elevation_m"]["point"]), "NASADEM"

    needed = {"T2M", "T2M_MAX", "T2M_MIN", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN", "PRECTOTCORR"}
    if power is not None and needed <= set(power.columns):
        c = power.col
        variants = {"viento_power": c("WS2M"), "viento_fao56_2ms": np.full(len(power), FAO56_DEFAULT_U2)}
        e6: dict[str, Any] = {"titulo": "Balance de agua preliminar", "elevacion_m": elev_m, "elevacion_fuente": elev_src, "supuestos": ["G = 0", "albedo 0.23", f"elevación {elev_m:g} m ({elev_src})", "ea con HR media y T media"], "variantes": {}}
        for name, u2 in variants.items():
            et = et0_pm(power.dates, params.lat, elev_m, c("T2M"), c("T2M_MAX"), c("T2M_MIN"), c("RH2M"), u2, c("ALLSKY_SFC_SW_DWN"))
            bal_m, bal_v = monthly(power.dates, c("PRECTOTCORR") - et, "sum")
            cal = bal_m.astype(int) % 12 + 1
            p50 = {int(m): round(float(np.median(bal_v[cal == m])), 1) for m in range(1, 13) if (cal == m).any()}
            v: dict[str, Any] = {"et0_mediana_mm_dia": round(float(np.nanmedian(et)), 2), "et0_anual_mediana_mm": round(float(np.median(annual_totals(power.dates, et)))),
                                 "balance_mensual_p50_mm": p50, "meses_con_balance_negativo_p50": [m for m, x in p50.items() if x < 0],
                                 "racha_seca_mas_larga_por_anio_dias": dry_spells(power.dates, c("PRECTOTCORR"), wet_mm)}
            if om is not None and "et0_fao_evapotranspiration" in om.columns:
                common, ia, ib = np.intersect1d(power.dates, om.dates, return_indices=True)
                x, y = et[ia], om.col("et0_fao_evapotranspiration")[ib]
                ok = ~np.isnan(x) & ~np.isnan(y)
                if ok.sum() > 30:
                    v["vs_openmeteo"] = {"corr_diaria": corr(x[ok], y[ok]), "sesgo_pct": round(100 * float((x[ok].sum() - y[ok].sum()) / y[ok].sum()), 1)}
            e6["variantes"][name] = v
        if (b := e6["variantes"]["viento_power"].get("vs_openmeteo")) and abs(b["sesgo_pct"]) > ET0_DIFF_WARN:
            warnings.append(f"ET0 con el viento de POWER difiere {b['sesgo_pct']} % de la de Open-Meteo (> {ET0_DIFF_WARN:g} %)")
        stages["E6"] = e6
    else:
        stages["E6"] = {"titulo": "Balance de agua preliminar", "estado": "por integrar: POWER no llegó completo"}

    stages["E7"] = {"titulo": "Terreno (NASADEM)", **nd} if nd is not None else {"titulo": "Terreno (NASADEM)", "estado": "por integrar: NASADEM no llegó"}

    plan, stop = degradation_plan(results)
    return {
        "meta": {"lon": params.lon, "lat": params.lat, "plot_side_m": params.plot_side_m, "start": params.start, "end": params.end, "elev_m": elev_m,
                 "umbrales_propuestos": {"cloud_max_pct": cloud_max, "dia_lluvioso_mm": wet_mm, "sesgo_lluvia_pct": RAIN_BIAS_WARN, "diferencia_et0_pct": ET0_DIFF_WARN, "borde_descartado_m": 30}},
        "stages": stages, "warnings": warnings, "decisions": plan,
        "decision_entrega": "DETENER: falta una fuente del núcleo sin respaldo" if stop else "PUBLICAR con avisos",
        "nucleo": CORE,
    }
