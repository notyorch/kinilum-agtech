"""El EDA: cada función contra entradas con respuesta conocida. Los datos sintéticos son solo entradas de prueba."""

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from ingest import eda
from ingest.contract import Fetch, Provenance, Series
from ingest.load import Params, Result


def days(start: str, end: str) -> np.ndarray:
    return np.arange(np.datetime64(start), np.datetime64(end) + np.timedelta64(1, "D"), dtype="datetime64[D]")


def test_monthly_keeps_only_complete_months():
    d = days("2024-01-15", "2024-03-31")  # enero queda incompleto
    months, totals = eda.monthly(d, np.ones(len(d)), "sum")
    assert [str(m) for m in months] == ["2024-02", "2024-03"] and totals.tolist() == [29.0, 31.0]


def test_a_missing_day_makes_its_month_incomplete():
    d = days("2024-02-01", "2024-03-31")
    v = np.ones(len(d))
    v[3] = np.nan
    months, _ = eda.monthly(d, v, "sum")
    assert [str(m) for m in months] == ["2024-03"]


def test_monthly_percentiles_are_taken_across_years():
    d = days("2020-01-01", "2024-12-31")
    v = np.where(d.astype("datetime64[M]").astype(int) % 12 == 5, 10.0, 0.0)  # cada junio: 10 mm por día
    out = eda.monthly_percentiles(d, v, "sum")
    assert out[6]["p50"] == 300.0 and out[6]["anios"] == 5 and out[1]["p50"] == 0.0


def test_coverage_finds_the_longest_gap_on_the_full_daily_grid():
    d = days("2024-01-01", "2024-01-10")
    col = np.ones(len(d))
    col[3:7] = np.nan
    cov = eda.coverage(Series(d, {"x": col}))["x"]
    assert (cov["dias_esperados"], cov["dias_con_dato"], cov["hueco_mas_largo_dias"], cov["cobertura_pct"]) == (10, 6, 4, 60.0)


def test_quality_flags_values_out_of_physical_range_and_unbelievable_wind():
    d = days("2024-01-01", "2024-01-05")
    q = eda.quality(Series(d, {"RH2M": np.array([50, 60, 150, 70, 80.0]), "WS2M": np.zeros(5)}))
    assert q["RH2M"]["fuera_de_rango"] == 1 and "mediana_inverosimil" not in q["RH2M"]
    assert q["WS2M"]["mediana"] == 0.0 and "viento" in q["WS2M"]["mediana_inverosimil"]
    assert q["_duplicados_indice"]["n"] == 0


def test_rain_agreement_of_a_series_with_itself_is_perfect_and_a_scaled_copy_shows_the_bias():
    d = days("2020-01-01", "2022-12-31")
    rain = np.where(np.arange(len(d)) % 3 == 0, 8.0, 0.0)
    a = Series(d, {"r": rain})
    same = eda.rain_agreement(a, "r", a, "r")
    assert (same["corr_mensual"], same["sesgo_pct_total"], same["acuerdo_lluvioso_seco_pct"]) == (1.0, 0.0, 100.0)
    scaled = eda.rain_agreement(Series(d, {"r": rain * 0.7}), "r", a, "r")
    assert scaled["sesgo_pct_total"] == -30.0 and scaled["acuerdo_lluvioso_seco_pct"] == 100.0
    # Signo: negativo = la primera serie llueve MENOS que la segunda; y los totales anuales lo muestran a la vista.
    assert scaled["definicion_sesgo"] == "(primera − segunda) / segunda"
    assert scaled["anual_mediana_mm_primera"] == pytest.approx(scaled["anual_mediana_mm_segunda"] * 0.7, abs=1)


def test_a_constant_series_has_no_correlation_instead_of_nan():
    assert eda.corr(np.ones(10), np.arange(10.0)) is None and eda.corr(np.arange(2.0), np.arange(2.0)) is None
    assert eda.corr(np.arange(10.0), np.arange(10.0) * 2) == 1.0


def test_rain_agreement_with_almost_no_common_days_says_so():
    a, b = Series(days("2024-01-01", "2024-01-05"), {"r": np.ones(5)}), Series(days("2024-01-04", "2024-01-09"), {"r": np.ones(6)})
    assert "nota" in eda.rain_agreement(a, "r", b, "r")


def tropical(n: int = 1, u2: float = 2.0) -> dict:
    ones = np.ones(n)
    return dict(t=27 * ones, tmax=33 * ones, tmin=22 * ones, rh=70 * ones, u2=u2 * ones, rs_mj=20 * ones)


def test_et0_is_in_the_known_range_for_a_tropical_day_and_grows_with_wind():
    d = days("2024-06-15", "2024-06-15")
    calm = eda.et0_pm(d, 20.3, 40, **tropical(u2=0.0))[0]
    windy = eda.et0_pm(d, 20.3, 40, **tropical(u2=2.0))[0]
    assert 3.5 < windy < 7.0       # orden de magnitud de un día de verano a 20° N
    assert windy > calm * 1.05     # más viento, más evaporación: por eso importa que POWER dé viento casi cero


def test_et0_never_goes_negative():
    d = days("2024-12-21", "2024-12-21")
    out = eda.et0_pm(d, 60.0, 0, **{**tropical(), "rs_mj": np.array([0.5])})
    assert out[0] >= 0


def test_dry_spells_count_consecutive_days_below_the_threshold_per_year():
    d = days("2023-01-01", "2024-12-31")
    rain = np.full(len(d), 5.0)
    rain[10:40] = 0.0   # 2023: 30 días secos seguidos
    rain[400:410] = 0.5  # 2024: 10
    s = eda.dry_spells(d, rain)
    assert s["p50"] == 20.0 and s["p90"] == pytest.approx(28.0) and s["p10"] == pytest.approx(12.0)


def scene(day: str, cloud, sid: str) -> dict:
    return {"id": sid, "collection": "x", "datetime": datetime.fromisoformat(day).replace(tzinfo=timezone.utc), "cloud": cloud}


def test_scene_summary_counts_clean_scenes_and_months_without_one():
    scenes = [scene("2024-01-05", 10, "a"), scene("2024-01-20", 90, "b"), scene("2024-03-02", 20, "c"), scene("2024-03-09", None, "d")]
    s = eda.scene_summary(scenes, "2024-01-01", "2024-04-30", cloud_max=30)
    assert (s["escenas"], s["escenas_limpias"], s["meses_en_el_periodo"]) == (4, 2, 4)
    assert s["meses_sin_escena_limpia"] == ["2024-02", "2024-04"] and s["escenas_limpias_por_mes_del_anio"][3] == 1
    assert s["meses_sin_ninguna_escena"] == ["2024-02", "2024-04"] and s["meses_solo_con_nubes"] == [] and s["primera_escena"] == "2024-01-05"


def test_cloudy_months_are_told_apart_from_months_with_no_scenes_at_all():
    s = eda.scene_summary([scene("2024-01-05", 90, "a"), scene("2024-03-02", 20, "b")], "2024-01-01", "2024-03-31")
    assert s["meses_solo_con_nubes"] == ["2024-01"] and s["meses_sin_ninguna_escena"] == ["2024-02"]


ALL = ("power", "imerg", "hls_stac", "nasadem", "modis", "smap", "ecostress", "grace", "openmeteo", "soilgrids", "s2_earthsearch", "era5land")


def results(default: str = "pending", **override: str) -> dict:
    """Un resultado por fuente: `default` para todas y `override` para las que se quieran distintas."""
    return {sid: Result(sid, override.get(sid, default), "") for sid in ALL}


def test_degradation_plan_stops_when_a_core_source_has_no_backup():
    plan, stop = eda.degradation_plan(results(power="ok", hls_stac="ok", openmeteo="ok"))
    assert stop is True
    by = {p["fuente"]: p for p in plan}
    assert "SIN RESPALDO" in by["nasadem"]["accion"] and "Open-Meteo" in by["imerg"]["accion"]
    assert by["smap"]["aviso_en_pantalla"] == "Humedad estimada" and by["grace"]["aviso_en_pantalla"] == "ninguno"


def test_degradation_plan_with_everything_in_place_has_nothing_to_do():
    plan, stop = eda.degradation_plan(results("ok"))
    assert (plan, stop) == ([], False)


def test_hls_falls_back_to_sentinel_2_with_a_lower_support_level():
    plan, stop = eda.degradation_plan(results("ok", hls_stac="no_data"))
    assert not stop and plan[0]["fuente"] == "hls_stac" and plan[0]["aviso_en_pantalla"] == "Entorno"


def synthetic_power(years: int = 3) -> Series:
    d = days("2021-01-01", f"{2020 + years}-12-31")
    n = len(d)
    doy = (d - d.astype("datetime64[Y]")).astype(int)
    wet = np.where((doy > 150) & (doy < 300), 6.0, 0.2)
    cols = {"PRECTOTCORR": wet, "T2M": 26 + 3 * np.sin(doy / 58), "T2M_MAX": 32 + 4 * np.sin(doy / 58), "T2M_MIN": 21 + 2 * np.sin(doy / 58),
            "RH2M": np.full(n, 72.0), "WS2M": np.full(n, 0.1), "ALLSKY_SFC_SW_DWN": np.full(n, 19.0)}
    return Series(d, cols, {"ALLSKY_SFC_SW_DWN": "MJ/m^2/day"})


def fetched(sid: str, data) -> Result:
    return Result(sid, "ok", "", Fetch(data, Provenance(sid, "p", "e", {}), notes=[]))


def test_the_report_runs_on_what_arrived_and_declares_what_did_not():
    p = synthetic_power()
    om = Series(p.dates, {"precipitation_sum": p.col("PRECTOTCORR") * 1.4, "et0_fao_evapotranspiration": np.full(len(p), 4.5)})
    res = {**results(), "power": fetched("power", p), "openmeteo": fetched("openmeteo", om)}
    report = eda.build_report(res, Params(-89.42, 20.30, "2021-01-01", "2023-12-31"))
    st = report["stages"]
    assert set(st) == {"E0", "E1", "E2", "E3", "E4", "E5", "E6"}
    assert st["E4"]["pares"]["POWER vs Open-Meteo"]["sesgo_pct_total"] == pytest.approx(-28.6, abs=0.1)
    assert any("Sesgo de lluvia" in w for w in report["warnings"]) and any("viento" in w for w in report["warnings"])
    assert report["decision_entrega"].startswith("DETENER")
    json.dumps(report, default=str, allow_nan=False)  # ningún NaN: sería un JSON inválido
    v = st["E6"]["variantes"]
    assert v["viento_fao56_2ms"]["et0_anual_mediana_mm"] > v["viento_power"]["et0_anual_mediana_mm"]
    e5 = {r["id"]: r for r in st["E5"]["fuentes"]}
    assert e5["hls_stac"]["pixeles_limpios_en_parcela"] == 16 and e5["power"]["soporte_efectivo"] == "region" and e5["imerg"]["soporte_efectivo"] == "sin_dato"


def test_the_report_without_power_says_por_integrar_and_does_not_invent():
    report = eda.build_report(results(), Params(-89.42, 20.30, "2021-01-01", "2023-12-31"))
    assert report["stages"]["E3"]["estado"].startswith("por integrar") and report["stages"]["E6"]["estado"].startswith("por integrar")
    assert report["decision_entrega"].startswith("DETENER")
