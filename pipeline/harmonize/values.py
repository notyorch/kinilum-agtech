"""De lo que dicen las fuentes a los valores del contrato (`ContractValue`): el paso de bronce a oro.

Cada valor nace con su rango, su nivel de soporte y su procedencia. Si no hay con qué calcularlo, sale SIN DATO
(`value: null`, sin rango), nunca rellenado. Solo se construyen los que ya tienen fuente:

  - `rain`  (GPM IMERG, zona): lluvia de mayo a octubre; mediana y rango entre años completos.
  - `slope` (NASADEM, parcela): pendiente de los píxeles limpios de la parcela.

`bare`, `heat`, `soil` y `moisture` faltan: esperan píxeles de HLS, la definición de «temperatura máxima de mayo»,
la profundidad que declara el técnico y SMAP. Con valores incompletos no se arma el paquete (`package/build.py`).
"""

from __future__ import annotations

import calendar
from functools import lru_cache
from typing import Any

import numpy as np
import yaml

from common.schema import REPO
from harmonize.cover import bare_value
from ingest.contract import Fetch, Provenance, contract_value
from ingest.imerg import NATIVE_RES_M as IMERG_RES_M
from ingest.smap import NATIVE_RES_M as SMAP_RES_M
from ingest.load import Result

RAIN_MONTHS = tuple(range(5, 11))  # mayo a octubre
MIN_YEARS = 3  # con menos años completos no hay rango que valga
HEAT_MONTH = 5  # «temperatura máxima de mayo»
POWER_RES_M = 55_000
SOILGRIDS_RES_M = 250
MIN_COVERAGE = 0.8  # fracción mínima de días con dato para que SMAP sostenga un valor
SOIL_RULES_PATH = REPO / "pipeline" / "rules" / "soil.v1.yaml"


@lru_cache(maxsize=None)
def soil_rules() -> dict[str, Any]:
    return yaml.safe_load(SOIL_RULES_PATH.read_text(encoding="utf-8"))


def season_totals(dates: np.ndarray, rain: np.ndarray, months: tuple[int, ...] = RAIN_MONTHS) -> dict[int, float]:
    """Total de lluvia (mm) de los `months` de cada año, solo de los años con TODOS sus días y sin faltantes."""
    years = dates.astype("datetime64[Y]").astype(int) + 1970
    month = dates.astype("datetime64[M]").astype(int) % 12 + 1
    out: dict[int, float] = {}
    for y in np.unique(years):
        window = (years == y) & np.isin(month, months)
        expected = sum(calendar.monthrange(int(y), m)[1] for m in months)
        if window.sum() == expected and not np.isnan(rain[window]).any():
            out[int(y)] = float(rain[window].sum())
    return out


def rain_value(fetch: Fetch) -> dict[str, Any]:
    """`rain_season`: lluvia de mayo a octubre (IMERG). Mediana, p10 y p90 entre los años completos."""
    series = fetch.data
    totals = season_totals(series.dates, series.col("precip_mm_day"))
    cell = fetch.prov.params.get("cell", {})
    where = f"celda centrada en {cell['lon_center']}, {cell['lat_center']}" if cell else "celda del punto"
    common = dict(unit="mm", prov=fetch.prov, native_resolution="0.1°", native_res_m=IMERG_RES_M, method="modeled", assumptions=["contextOnly"])
    if len(totals) < MIN_YEARS:
        return contract_value("rain_season", None, None, None, timestamp="2025", extra_steps=[f"sin dato: {len(totals)} años completos de mayo a octubre y se necesitan {MIN_YEARS}"], **common)
    vals = np.array(list(totals.values()))
    years = sorted(totals)
    return contract_value(
        "rain_season", float(np.median(vals)), float(np.percentile(vals, 10)), float(np.percentile(vals, 90)),
        timestamp=str(years[-1]),
        extra_steps=["agg: suma de mayo a octubre de cada año", f"p10, mediana y p90 entre {len(years)} años completos ({years[0]}–{years[-1]})", where],
        **common,
    )


def slope_value(fetch: Fetch) -> dict[str, Any]:
    """`slope`: pendiente (%) de los píxeles limpios de la parcela. Mediana, p10 y p90 entre píxeles."""
    s = fetch.data["slope_pct"]
    return contract_value(
        "slope", s["p50"], s["p10"], s["p90"], "%", fetch.prov, "30 m", 30, "measured", "2000-02",
        assumptions=["innerBuffer"],
        extra_steps=[f"{fetch.data['clean_cells']} píxeles limpios tras descartar 30 m de borde", "pendiente por el método de Horn", "p10, mediana y p90 entre píxeles"],
    )


def month_peaks(dates: np.ndarray, values: np.ndarray, month: int) -> dict[int, float]:
    """El máximo de `values` en el mes `month` de cada año, solo de los años con todos los días del mes y sin faltantes."""
    years = dates.astype("datetime64[Y]").astype(int) + 1970
    months = dates.astype("datetime64[M]").astype(int) % 12 + 1
    out: dict[int, float] = {}
    for y in np.unique(years):
        window = (years == y) & (months == month)
        if window.sum() == calendar.monthrange(int(y), month)[1] and not np.isnan(values[window]).any():
            out[int(y)] = float(values[window].max())
    return out


def heat_value(fetch: Fetch) -> dict[str, Any]:
    """`tmax_may`: temperatura máxima de mayo (POWER, región): el día más caluroso de cada mayo, y su mediana y rango entre años.

    Se eligió el máximo del mes, no el promedio de las máximas, porque el calor que daña al cultivo es el extremo y
    porque así lo definía el paquete de ejemplo (`agg: monthly max`). El promedio de las máximas diarias de mayo va
    en el informe del EDA. Los días de calor en la floración se cuentan aparte (`phenology.heat_days_in_window`).
    """
    series = fetch.data
    peaks = month_peaks(series.dates, series.col("T2M_MAX"), HEAT_MONTH)
    common = dict(unit="°C", prov=fetch.prov, native_resolution="0.5° × 0.625°", native_res_m=POWER_RES_M, method="modeled", assumptions=["modeledClimate"])
    if len(peaks) < MIN_YEARS:
        return contract_value("tmax_may", None, None, None, timestamp="2025", extra_steps=[f"sin dato: {len(peaks)} años con el mes de mayo completo y se necesitan {MIN_YEARS}"], **common)
    vals = np.array(list(peaks.values()))
    years = sorted(peaks)
    return contract_value(
        "tmax_may", float(np.median(vals)), float(np.percentile(vals, 10)), float(np.percentile(vals, 90)), timestamp=str(years[-1]),
        extra_steps=["T2M_MAX: temperatura máxima diaria a 2 m", "agg: máximo de mayo de cada año", f"p10, mediana y p90 entre {len(years)} años completos ({years[0]}–{years[-1]})", "sin regrilla: la celda de POWER del punto"],
        **common,
    )


def moisture_value(fetch: Fetch) -> dict[str, Any]:
    """`soil_moisture_rootzone`: humedad de la zona de raíz (SMAP L4, zona). Mediana de la muestra diaria y rango entre días.

    Es CONTEXTO de zona («en su zona»), nunca color dentro de la parcela. Con menos del 80 % de los días, sale sin dato.
    """
    series = fetch.data
    root = series.col("sm_rootzone")
    ok = ~np.isnan(root)
    cell = fetch.prov.params.get("cell", {})
    common = dict(unit="m³/m³", prov=fetch.prov, native_resolution="9 km", native_res_m=SMAP_RES_M, method="modeled", assumptions=["contextOnly"])
    if ok.sum() < MIN_COVERAGE * len(root):
        return contract_value("soil_moisture_rootzone", None, None, None, timestamp="2025", extra_steps=[f"sin dato: {int(ok.sum())} de {len(root)} días con dato y se necesita al menos el {MIN_COVERAGE:.0%}"], **common)
    vals = root[ok]
    first, last = series.dates[ok][0], series.dates[ok][-1]
    where = f"celda centrada en {cell['lon_center']}, {cell['lat_center']}" if cell else "celda del punto"
    return contract_value(
        "soil_moisture_rootzone", float(np.median(vals)), float(np.percentile(vals, 10)), float(np.percentile(vals, 90)), timestamp=str(last)[:7],
        extra_steps=["sm_rootzone: humedad de la zona de raíz (0–100 cm)", f"un granulo por día ({fetch.prov.params.get('hhmm_utc', '16:30')} UTC) entre {first} y {last}", f"mediana, p10 y p90 entre {int(ok.sum())} días", where],
        **common,
    )


def soil_value(config: dict[str, Any], generated_at: str) -> dict[str, Any]:
    """`root_depth`: profundidad efectiva de raíz que DECLARA el técnico (`soil` en la parcela); no sale de SoilGrids.

    Con medición de campo (`root_depth_cm`) el valor es esa medición. Si no, es la mitad del rango del tipo de suelo
    y el rango entero es p10–p90: un supuesto del equipo, a validar con el técnico.
    """
    rules = soil_rules()
    kind = config["soil"]
    name = rules["nombre"][kind]
    declared = Provenance(name, f"declarado por el técnico ({kind})", "pipeline/parcels", {"soil": kind})
    common = dict(unit="cm", prov=declared, native_resolution="declared", native_res_m=0, timestamp=generated_at[:7])
    if config.get("root_depth_cm") is not None:
        cm = float(config["root_depth_cm"])
        return contract_value("root_depth", cm, cm, cm, method="measured", assumptions=[], provenance=["medición de campo declarada por el técnico (root_depth_cm)"], **common)
    lo, hi = rules["profundidad_raiz_cm"][kind]
    return contract_value(
        "root_depth", (lo + hi) / 2, lo, hi, method="assumed", assumptions=list(rules["supuestos"][kind]),
        provenance=[f"{name}: {lo}–{hi} cm, supuesto del equipo a validar con el técnico", f"reglas {rules['rules_version']}", "el valor es la mitad del rango; el rango es p10–p90"],
        **common,
    )


def missing_value(variable: str, unit: str, source: str, native_resolution: str, native_res_m: float, reason: str) -> dict[str, Any]:
    """Un valor SIN DATO del contrato (sin valor ni rango) para una fuente que no llegó, con la razón en la procedencia."""
    prov = Provenance(source, "sin respuesta", "", {})
    return contract_value(variable, None, None, None, unit, prov, native_resolution, native_res_m, "modeled", "2025", assumptions=["contextOnly"], provenance=[f"{source}: sin dato", reason])


def clay_value(fetch: Fetch) -> dict[str, Any]:
    """`clay_0_5cm`: arcilla de 0 a 5 cm (SoilGrids, entorno). Es CONTEXTO: el paquete no la usa.

    Nunca convierte un nulo a número: sin valor en la capa, sale sin dato. El rango son los cuantiles 5 y 95 (SoilGrids no
    da el 10 y el 90). Si el punto no tenía valores y se usó la celda válida más cercana, el método es `interpolated` y la
    procedencia dice a cuántos metros y hacia dónde.
    """
    row = next((r for r in fetch.data if r["property"] == "clay" and r["depth"] == "0-5cm"), None)
    fallback = fetch.prov.params.get("fallback")
    method = "interpolated" if fallback else "modeled"
    steps = ["clay, 0-5 cm", "rango = cuantiles 5 y 95, no 10 y 90"]
    if fallback:
        steps.append(f"el punto no tenía valores: celda válida más cercana, a {fallback['distance_m']} m al {fallback['direction']}")
    common = dict(unit="%", prov=fetch.prov, native_resolution="250 m", native_res_m=SOILGRIDS_RES_M, method=method, assumptions=["contextOnly"], timestamp="2025")
    if row is None or row["mean"] is None or row["q05"] is None or row["q95"] is None:
        return contract_value("clay_0_5cm", None, None, None, extra_steps=[*steps, "sin dato: la capa no trae valor o le faltan los cuantiles"], **common)
    return contract_value("clay_0_5cm", row["mean"], row["q05"], row["q95"], extra_steps=steps, **common)


def context_values(results: dict[str, Result]) -> dict[str, dict[str, Any]]:
    """Valores de CONTEXTO (complementos que el paquete no usa). Una fuente que no llegó sale sin dato, nunca ausente."""
    r = results.get("soilgrids")
    if r is None:
        return {}
    if r.fetch:
        return {"clay_0_5cm": clay_value(r.fetch)}
    return {"clay_0_5cm": missing_value("clay_0_5cm", "%", "SoilGrids (ISRIC)", "250 m", SOILGRIDS_RES_M, r.detail or "la fuente no llegó")}


def partial_values(results: dict[str, Result], config: dict[str, Any] | None = None, generated_at: str = "") -> dict[str, dict[str, Any]]:
    """Los valores del contrato que ya se pueden construir con lo que llegó. Los demás no aparecen: no hay fuente.

    `soil` sale de lo que declara el técnico (la configuración de la parcela), no de una fuente que se pida.
    """
    out: dict[str, dict[str, Any]] = {}
    if config is not None:
        out["soil"] = soil_value(config, generated_at)
    if "imerg" in results and results["imerg"].fetch:
        out["rain"] = rain_value(results["imerg"].fetch)
    if "nasadem" in results and results["nasadem"].fetch:
        out["slope"] = slope_value(results["nasadem"].fetch)
    if "power" in results and results["power"].fetch:
        out["heat"] = heat_value(results["power"].fetch)
    if "smap" in results and results["smap"].fetch:
        out["moisture"] = moisture_value(results["smap"].fetch)
    if "hls_ndvi" in results and results["hls_ndvi"].fetch:
        out["bare"] = bare_value(results["hls_ndvi"].fetch)
    return out
