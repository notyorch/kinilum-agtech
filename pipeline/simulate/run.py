"""Paso 3 del pipeline: simulador de rotación (plata → oro).

    python -m simulate.run --parcel sin-demo-001 --lon -108.45673 --lat 25.50826

Lee de la caché de bronce (sin pedir nada a la red) la lluvia de IMERG, la temperatura de POWER y la elevación de
NASADEM, y escribe en pipeline/data/gold/<parcela>/ el bloque `simulation.json` del paquete (shared/schema: Simulation)
y `simulation_summary.json`, un resumen legible.

Qué calcula (v1) y qué NO:
  - AGUA: necesidad de riego de un ciclo de maíz y de uno del cultivo de rotación (ETc de FAO-56 − lluvia), y su promedio
    por estrategia. ET0 de Penman–Monteith con la temperatura de POWER (viento de 2 m/s, humedad relativa constante).
  - INGRESO: rendimiento × precio medio rural del SIAP (Guasave, otoño-invierno, riego), del mismo año de la tabla. Es
    ingreso BRUTO por hectárea: no hay costos. No depende del clima simulado.
  - SUELO, EROSIÓN y CLIMA: sin dato. No hay cifras de nitrógeno ni de erosión por estrategia, y el calor que daña solo lo
    tiene el sorgo. Se declaran en `no_data`; no se inventan.
  - E1 (maíz con cobertura): sin dato en los cinco criterios; no hay datos de agua ni de costo de la cobertura.

Cada corrida es un año real de la lluvia y la temperatura de la zona (2016–2024), tomados JUNTOS, con una fecha de siembra
al azar dentro de la ventana del INIFAP y un año al azar de rendimiento y precio. Cada celda cambia lluvia (%) y
temperatura (°C) de esos años. La corrida i es el mismo año simulado para las seis estrategias.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from common.schema import REPO
from harmonize.phenology import maize_rules  # noqa: F401  (la regla de floración vive ahí; aquí solo se usa el catálogo)
from ingest.contract import Series
from ingest.eda import et0_pm

from . import model
from .crops import RULES_DIR, crop_profile, load_catalog
from .encode import cell_to_json
from .scenarios import CRITERIA, ROTATION_CROP, STRATEGIES, cells

SEED = 20261115
SEASON_YEARS = range(2016, 2025)  # temporadas de octubre a septiembre con IMERG completo
PRICE_YEARS = range(2020, 2025)  # los precios son corrientes: solo los años recientes
U2_DEFAULT = 2.0
GDD_HARVEST = 1640.7  # INIFAP, Tabla 20: grados día acumulados a cosecha (híbrido de ciclo intermedio)
WATER_CEILING_PERCENTILE = 95
GENERATOR = "simulate.run v1 · ETc de FAO-56 − lluvia; INIFAP; SIAP"
NO_DATA = {"E0": ["soil", "erosion", "climate"], "E1": list(CRITERIA), **{s: ["soil", "erosion", "climate"] for s in ("E2", "E3", "E4", "E5")}}


def season_arrays(power: Series, imerg: Series, year: int) -> dict[str, np.ndarray] | None:
    """Los días del 1 de octubre de `year` al 30 de septiembre del siguiente, o None si falta algún día de alguna fuente."""
    start, end = np.datetime64(f"{year}-10-01"), np.datetime64(f"{year + 1}-09-30")
    out: dict[str, np.ndarray] = {}
    for name, series, col in (("t", power, "T2M"), ("tmax", power, "T2M_MAX"), ("tmin", power, "T2M_MIN"), ("rh", power, "RH2M"), ("rs", power, "ALLSKY_SFC_SW_DWN"), ("rain", imerg, "precip_mm_day")):
        idx = (series.dates >= start) & (series.dates <= end)
        vals = series.col(col)[idx]
        if len(vals) != (end - start).astype(int) + 1 or np.isnan(vals).any():
            return None
        out[name] = vals
    out["dates"] = power.dates[(power.dates >= start) & (power.dates <= end)]
    return out


def et0_for(season: dict[str, np.ndarray], dtemp: float, lat: float, elev_m: float) -> np.ndarray:
    return et0_pm(season["dates"], lat, elev_m, season["t"] + dtemp, season["tmax"] + dtemp, season["tmin"] + dtemp, season["rh"], np.full(len(season["t"]), U2_DEFAULT), season["rs"])


def crop_specs(variant: str | None) -> dict[str, dict[str, Any]]:
    """Lo que el simulador necesita de cada cultivo: Kc, etapas, ventana de siembra y ciclo (o los grados día del maíz)."""
    catalog = load_catalog()
    specs: dict[str, dict[str, Any]] = {}
    maiz = catalog["maiz_base"]
    specs["maiz"] = {"kc": maiz["kc_por_etapa"], "stages": maiz["etapas_dias_fao56"], "window": maiz["ventana_siembra"], "cycle": None}
    for crop in ROTATION_CROP.values():
        p = crop_profile(crop, variant if crop == "frijol" else None)
        c = p["ciclo_dias"]
        specs[crop] = {"kc": p["kc_por_etapa"], "stages": p["etapas_dias_fao56"], "window": p["ventana_siembra"], "cycle": int(round((c["min"] + c["max"]) / 2 + 1e-9))}
    return specs


def siap_revenue(table: dict[str, Any]) -> dict[str, np.ndarray]:
    """Ingreso bruto por hectárea (pesos) de cada año de PRICE_YEARS: rendimiento × precio medio rural del mismo año."""
    years = table["anios"]
    pick = [years.index(y) for y in PRICE_YEARS]
    return {crop: np.array([rows["rendimiento_t_ha"][i] * rows["pmr_mxn_t"][i] for i in pick]) for crop, rows in table["cultivos"].items()}


def simulate(seasons: list[dict[str, np.ndarray]], lat: float, elev_m: float, specs: dict[str, dict[str, Any]], revenue: dict[str, np.ndarray], *, seed: int = SEED) -> dict[str, Any]:
    """Todas las celdas: necesidad de riego (mm) e ingreso ($/ha) por estrategia y corrida, y los puntajes."""
    rng = np.random.default_rng(seed)
    et0_cache = {(dt, i): et0_for(s, dt, lat, elev_m) for dt in {c.temp for c in cells()} for i, s in enumerate(seasons)}
    strategy_crop = {"E0": None, **ROTATION_CROP}
    raw: list[dict[str, np.ndarray]] = []
    for cell in cells():
        n = cell.runs
        season_idx = rng.integers(0, len(seasons), n)
        sow_u = {c: rng.random(n) for c in specs}
        year_idx = rng.integers(0, len(PRICE_YEARS), n)
        need = {c: np.empty(n) for c in specs}
        for r in range(n):
            s = seasons[season_idx[r]]
            et0 = et0_cache[(cell.temp, season_idx[r])]
            rain = s["rain"] * (1 + cell.rain / 100)
            for crop, sp in specs.items():
                lo, hi = model.window_offset(sp["window"]["inicio"]), model.window_offset(sp["window"]["fin"])
                start = int(round(lo + sow_u[crop][r] * (hi - lo)))
                days = model.gdd_cycle_days(s["t"] + cell.temp, start, GDD_HARVEST) if sp["cycle"] is None else sp["cycle"]
                need[crop][r] = model.crop_need(et0, rain, start, days, sp["kc"], sp["stages"])["need"]
        strat_need = np.full((len(STRATEGIES), n), np.nan)
        strat_rev = np.full((len(STRATEGIES), n), np.nan)
        for i, st in enumerate(STRATEGIES):
            if st == "E1":
                continue
            crop = strategy_crop[st]
            strat_need[i] = need["maiz"] if crop is None else (need["maiz"] + need[crop]) / 2
            strat_rev[i] = revenue["maiz"][year_idx] if crop is None else (revenue["maiz"][year_idx] + revenue[crop][year_idx]) / 2
        raw.append({"need": strat_need, "revenue": strat_rev, "cell": cell, "maize_need": need["maiz"]})
    water_ceiling = float(np.percentile(np.concatenate([r["need"][0] for r in raw]), WATER_CEILING_PERCENTILE))
    income_ceiling = float(np.percentile(np.concatenate([r["revenue"][0] for r in raw]), 95))
    out_cells = []
    for r in raw:
        n = r["cell"].runs
        scores = np.full((len(STRATEGIES), len(CRITERIA), n), np.nan)
        scores[:, CRITERIA.index("water"), :] = model.need_score(r["need"], water_ceiling)
        scores[:, CRITERIA.index("income"), :] = model.income_score(r["revenue"], income_ceiling)
        js = cell_to_json(r["cell"], scores, NO_DATA)
        # Lo que pide cada estrategia, en mm: [p10, mediana, p90]. La app lo usa para decir qué parte cubriría con menos agua de riego.
        js["water_mm"] = {st: [round(float(np.percentile(r["need"][i], q)), 1) for q in (10, 50, 90)] for i, st in enumerate(STRATEGIES) if st != "E1"}
        out_cells.append(js)
    return {"cells": out_cells, "raw": raw, "water_ceiling_mm": water_ceiling, "income_ceiling_mxn_ha": income_ceiling}


def summary(result: dict[str, Any], specs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Un resumen legible: lo que sale en el escenario normal y en el seco y caluroso."""
    out: dict[str, Any] = {"water_ceiling_mm": round(result["water_ceiling_mm"]), "income_ceiling_mxn_ha": round(result["income_ceiling_mxn_ha"]), "escenarios": {}}
    for r in result["raw"]:
        name = r["cell"].scenario
        if name not in ("normal", "dry", "dryHot", "hot"):
            continue
        out["escenarios"][name] = {
            st: {"riego_mm_p50": round(float(np.nanmedian(r["need"][i]))), "riego_mm_p10": round(float(np.nanpercentile(r["need"][i], 10))), "riego_mm_p90": round(float(np.nanpercentile(r["need"][i], 90))), "ingreso_mxn_ha_p50": round(float(np.nanmedian(r["revenue"][i])))}
            for i, st in enumerate(STRATEGIES) if st != "E1"
        }
    return out


def load_inputs(parcel: str, lon: float, lat: float) -> tuple[list[dict[str, np.ndarray]], float, dict[str, Any]]:
    """Las series de la caché de bronce (sin pedir nada a la red): temporadas completas, elevación y la tabla del SIAP."""
    from ingest.http import Client
    from ingest.load import Params, load_sources

    params = Params(lon, lat, "2016-01-01", "2025-12-31", 200, 4, soil_fallback_m=1000)
    results = load_sources(Client(), params, enabled=["power", "imerg", "nasadem"], bronze_dir=REPO / "pipeline" / "data" / "bronze", parcel_id=parcel)
    missing = [k for k in ("power", "imerg") if results[k].fetch is None]
    if missing:
        raise SystemExit(f"faltan fuentes en la caché: {', '.join(missing)}; corra primero `python -m ingest.run`")
    power, imerg = results["power"].fetch.data, results["imerg"].fetch.data
    seasons = [s for y in SEASON_YEARS if (s := season_arrays(power, imerg, y)) is not None]
    nas = results.get("nasadem")
    elev = float(nas.fetch.data["elevation_m"]["point"]) if nas is not None and nas.fetch is not None and nas.fetch.data["elevation_m"].get("point") is not None else 15.0
    table = yaml.safe_load((RULES_DIR / "sources" / "siap_guasave_oi_riego.yaml").read_text(encoding="utf-8"))
    return seasons, elev, table


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parcel", default="sin-demo-001")
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    args = ap.parse_args(argv)
    from package.build import load_config

    config = load_config(args.parcel)
    seasons, elev, table = load_inputs(args.parcel, args.lon, args.lat)
    specs = crop_specs(config.get("frijol_variante"))
    result = simulate(seasons, args.lat, elev, specs, siap_revenue(table))
    catalog = load_catalog()
    block = {"strategies": list(STRATEGIES), "criteria": list(CRITERIA), "rules_version": catalog["rules_version"], "no_data": NO_DATA, "generator": GENERATOR, "cells": result["cells"]}
    gold = REPO / "pipeline" / "data" / "gold" / args.parcel
    gold.mkdir(parents=True, exist_ok=True)
    (gold / "simulation.json").write_text(json.dumps(block, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    info = summary(result, specs)
    info["temporadas"] = len(seasons)
    (gold / "simulation_summary.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False, indent=1))
    print(f"simulation.json: {(gold / 'simulation.json').stat().st_size // 1024} KB, {len(seasons)} temporadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
