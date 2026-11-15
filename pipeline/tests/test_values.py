"""De las fuentes a los valores del contrato: lluvia de mayo a octubre y pendiente. Sin dato es sin dato."""

import numpy as np
import pytest

from harmonize import values
from ingest import nasadem
from ingest.contract import Fetch, Provenance, Series
from ingest.load import Result

CELL = {"lon_index": 905, "lat_index": 1103, "lon_center": -89.45, "lat_center": 20.35, "margin_deg": 0.0}


def days(start: str, end: str) -> np.ndarray:
    return np.arange(np.datetime64(start), np.datetime64(end) + np.timedelta64(1, "D"), dtype="datetime64[D]")


def rainy(first: int, last: int, factor=lambda y: 1.0) -> Series:
    """Cada año: 6 mm por día de mayo a octubre (× factor) y 0.2 el resto."""
    d = days(f"{first}-01-01", f"{last}-12-31")
    month = d.astype("datetime64[M]").astype(int) % 12 + 1
    year = d.astype("datetime64[Y]").astype(int) + 1970
    rain = np.where((month >= 5) & (month <= 10), 6.0, 0.2) * np.array([factor(int(y)) for y in year])
    return Series(d, {"precip_mm_day": rain, "neighbor_mm_day": rain * 0.5}, {"precip_mm_day": "mm/day"})


def imerg_fetch(series: Series) -> Fetch:
    return Fetch(series, Provenance("GPM IMERG Final (NASA GES DISC)", "GPM_3IMERGDF v07", "opendap", {"cell": CELL}, response_sha256="ab" * 32))


def test_only_complete_years_count_and_a_missing_day_drops_the_year():
    s = rainy(2021, 2023)
    totals = values.season_totals(s.dates, s.col("precip_mm_day"))
    assert totals == {2021: pytest.approx(1104.0), 2022: pytest.approx(1104.0), 2023: pytest.approx(1104.0)}
    partial = rainy(2021, 2023)
    cut = days("2021-01-01", "2023-08-31")  # 2023 termina en agosto: octubre no existe
    assert sorted(values.season_totals(cut, partial.col("precip_mm_day")[: len(cut)])) == [2021, 2022]
    holes = rainy(2021, 2023).col("precip_mm_day").copy()
    holes[(days("2021-01-01", "2023-12-31") == np.datetime64("2022-07-15"))] = np.nan
    assert sorted(values.season_totals(s.dates, holes)) == [2021, 2023]


def test_the_rain_value_is_the_median_of_may_to_october_with_the_range_between_years():
    s = rainy(2020, 2024, factor=lambda y: 1 + 0.1 * (y - 2020))  # 1104, 1214.4, …, 1545.6
    v = values.rain_value(imerg_fetch(s))
    assert v["variable"] == "rain_season" and v["unit"] == "mm" and v["support_level"] == "zone" and v["method"] == "modeled"
    # Totales 1104, 1214.4, 1324.8, 1435.2 y 1545.6: mediana en el centro; p10 y p90 por interpolación lineal.
    assert v["value"] == pytest.approx(1324.8, abs=0.1) and v["p10"] == pytest.approx(1148.2, abs=0.1) and v["p90"] == pytest.approx(1501.4, abs=0.1)
    assert v["p10"] <= v["value"] <= v["p90"] and v["timestamp"] == "2024" and v["assumptions"] == ["contextOnly"]
    steps = " | ".join(v["provenance"])
    assert "suma de mayo a octubre" in steps and "5 años completos (2020–2024)" in steps and "-89.45, 20.35" in steps


def test_with_fewer_than_three_complete_years_the_value_is_declared_without_data():
    v = values.rain_value(imerg_fetch(rainy(2023, 2024)))
    assert (v["value"], v["p10"], v["p90"]) == (None, None, None) and "se necesitan 3" in " ".join(v["provenance"])


def test_the_slope_value_comes_from_the_clean_pixels_of_the_plot():
    n = 3601
    res = 1 / (n - 1)
    dy, dx = nasadem.M_PER_DEG_LAT * res, nasadem.M_PER_DEG_LON_EQ * np.cos(np.radians(20.3)) * res
    tile = np.rint(100 + 0.50 * dx * np.arange(n)[None, :] + 0.20 * dy * np.arange(n)[:, None]).astype(">i2")
    f = Fetch(nasadem.terrain(tile, -89.42, 20.30), Provenance("NASADEM (NASA JPL / LP DAAC)", "NASADEM_HGT 001", "x", {}, response_sha256="cd" * 32))
    v = values.slope_value(f)
    assert (v["variable"], v["unit"], v["support_level"], v["method"], v["timestamp"], v["assumptions"]) == ("slope", "%", "parcel", "measured", "2000-02", ["innerBuffer"])
    assert v["value"] == pytest.approx(53.9, abs=1.0) and v["p10"] <= v["value"] <= v["p90"]
    assert any("píxeles limpios" in s for s in v["provenance"])


def test_only_the_values_that_have_a_source_are_built():
    assert values.partial_values({}) == {}
    only_rain = {"imerg": Result("imerg", "ok", "", imerg_fetch(rainy(2020, 2024))), "nasadem": Result("nasadem", "pending", "falta EARTHDATA_TOKEN")}
    assert list(values.partial_values(only_rain)) == ["rain"]


# ---- heat: temperatura máxima de mayo ------------------------------------------------------------------------------

def power_fetch(first: int, last: int, tmax_of=lambda y, m, d: 30.0) -> Fetch:
    d = days(f"{first}-01-01", f"{last}-12-31")
    year, month = d.astype("datetime64[Y]").astype(int) + 1970, d.astype("datetime64[M]").astype(int) % 12 + 1
    day = (d - d.astype("datetime64[M]")).astype(int) + 1
    tmax = np.array([tmax_of(int(y), int(m), int(k)) for y, m, k in zip(year, month, day)])
    return Fetch(Series(d, {"T2M_MAX": tmax}, {"T2M_MAX": "C"}), Provenance("NASA POWER", "daily point (AG)", "x", {}, response_sha256="ef" * 32))


def test_heat_is_the_hottest_day_of_each_may_with_its_median_and_range_between_years():
    # El día 10 de cada mayo es el más caluroso: 38, 39, 40, 41 y 42 °C de 2020 a 2024.
    f = power_fetch(2020, 2024, lambda y, m, d: 30.0 + (8 + (y - 2020) if (m == 5 and d == 10) else 0))
    v = values.heat_value(f)
    assert (v["variable"], v["unit"], v["support_level"], v["method"], v["timestamp"], v["assumptions"]) == ("tmax_may", "°C", "region", "modeled", "2024", ["modeledClimate"])
    assert v["value"] == 40.0 and v["p10"] == pytest.approx(38.4) and v["p90"] == pytest.approx(41.6)
    steps = " | ".join(v["provenance"])
    assert "máximo de mayo de cada año" in steps and "5 años completos (2020–2024)" in steps


def test_the_peak_is_not_the_average_and_incomplete_mays_are_dropped():
    f = power_fetch(2020, 2022, lambda y, m, d: 35.0 if m == 5 else 30.0)
    assert values.month_peaks(f.data.dates, f.data.col("T2M_MAX"), 5) == {2020: 35.0, 2021: 35.0, 2022: 35.0}
    holes = f.data.col("T2M_MAX").copy()
    holes[(f.data.dates == np.datetime64("2021-05-03"))] = np.nan
    assert sorted(values.month_peaks(f.data.dates, holes, 5)) == [2020, 2022]


def test_with_fewer_than_three_complete_mays_the_heat_is_declared_without_data():
    v = values.heat_value(power_fetch(2023, 2024))
    assert (v["value"], v["p10"], v["p90"]) == (None, None, None) and "se necesitan 3" in " ".join(v["provenance"])


# ---- Ventana de floración ------------------------------------------------------------------------------------------

def test_the_flowering_window_follows_the_sowing_month_and_the_stated_assumption():
    from harmonize import phenology as ph

    assert [str(d) for d in ph.flowering_window("june", 2024)] == ["2024-07-26", "2024-09-13"]
    assert [str(d) for d in ph.flowering_window("may", 2024)] == ["2024-06-25", "2024-08-14"]
    assert [str(d) for d in ph.flowering_window("july", 2024)] == ["2024-08-25", "2024-10-14"]
    with pytest.raises(ValueError, match="mes de siembra desconocido"):
        ph.flowering_window("agosto", 2024)


def test_the_flowering_assumptions_are_declared_as_assumptions_to_validate():
    from harmonize import phenology as ph

    r = ph.maize_rules()
    assert (r["estado_evidencia"], r["method"], r["fuente"], r["validado_por"]) == ("a_validar", "assumed", None, None)
    assert r["dias_a_floracion"] == [55, 75] and r["umbral_calor_c"] == 35


def test_heat_days_are_counted_only_inside_the_window_and_only_for_complete_years():
    from harmonize import phenology as ph

    f = power_fetch(2022, 2023, lambda y, m, d: 36.0 if (m, d) in {(8, 1), (8, 2), (8, 3)} or (m == 5 and d == 10) else 30.0)  # mayo queda fuera de la ventana
    assert ph.heat_days_in_window(f.data.dates, f.data.col("T2M_MAX"), "june") == {2022: 3, 2023: 3}
    cut = days("2022-01-01", "2023-08-31")  # 2023 se corta en agosto: su ventana (hasta el 13 de septiembre) no está completa
    assert sorted(ph.heat_days_in_window(cut, np.full(len(cut), 30.0), "june")) == [2022]


# ---- soil: lo que declara el técnico -------------------------------------------------------------------------------

@pytest.mark.parametrize("kind,name,lo,hi,assumptions", [
    ("tsekel", "Tsek'el", 15, 25, ["karstDepth", "teamAssumption"]),
    ("kankab", "K'ankab", 40, 60, ["teamAssumption"]),
    ("undeclared", "Sin declarar", 15, 60, ["karstDepth", "teamAssumption"]),
])
def test_the_declared_soil_gives_a_root_depth_range_that_is_an_assumption(kind, name, lo, hi, assumptions):
    v = values.soil_value({"soil": kind}, "2026-11-15")
    assert (v["variable"], v["unit"], v["source"], v["native_resolution"], v["support_level"], v["method"]) == ("root_depth", "cm", name, "declared", "parcel", "assumed")
    assert (v["value"], v["p10"], v["p90"]) == ((lo + hi) / 2, lo, hi) and v["assumptions"] == assumptions and v["timestamp"] == "2026-11"
    assert not any("pedido el" in step for step in v["provenance"])  # no se «pidió» a nadie: lo declaró el técnico


def test_a_field_measurement_replaces_the_range_and_is_measured():
    v = values.soil_value({"soil": "tsekel", "root_depth_cm": 18}, "2026-11-15")
    assert (v["value"], v["p10"], v["p90"], v["method"], v["assumptions"]) == (18.0, 18.0, 18.0, "measured", [])


def test_the_soil_rules_say_they_are_to_validate_and_do_not_come_from_soilgrids():
    r = values.soil_rules()
    assert (r["estado_evidencia"], r["method"], r["fuente"]) == ("a_validar", "assumed", None)
    assert set(r["profundidad_raiz_cm"]) == {"tsekel", "kankab", "undeclared"} == set(r["supuestos"]) == set(r["nombre"])


def test_the_declared_soil_joins_the_partial_values_without_any_source():
    out = values.partial_values({}, {"soil": "tsekel"}, "2026-11-15")
    assert list(out) == ["soil"] and out["soil"]["value"] == 20.0
