"""Temporadas del oro (falta de agua en la floración, lluvia de la temporada, normales y umbrales) con series sintéticas."""

from datetime import date

import numpy as np
import pytest

from harmonize import phenology, season
from ingest.contract import Series


def daily(start: str, end: str, value: float, name: str = "v") -> Series:
    dates = np.arange(np.datetime64(start), np.datetime64(end) + np.timedelta64(1, "D"))
    return Series(dates, {name: np.full(len(dates), value)})


def test_the_flowering_deficit_is_kc_times_et0_minus_rain_with_the_spread_between_sources():
    # siembra en diciembre de 2024 → ventana de floración de 2025, con los días que digan las reglas (INIFAP: 84 a 106)
    start, end = phenology.flowering_window("december", 2024)
    n = (end - start).days + 1
    rain_a, rain_b = daily("2024-01-01", "2025-12-31", 0.1, "r"), daily("2024-01-01", "2025-12-31", 0.2, "p")
    et_a, et_b = daily("2024-01-01", "2025-12-31", 4.0, "e"), daily("2024-01-01", "2025-12-31", 5.0, "e2")
    out = season.flowering_deficits("december", 1.2, [(rain_a, "r"), (rain_b, "p")], [(et_a, "e"), (et_b, "e2")])
    assert list(out) == [2025] and (start, end) == (date(2025, 2, 23), date(2025, 4, 16)) and n == 53
    combos = sorted(1.2 * et * n - r * n for et in (4.0, 5.0) for r in (0.1, 0.2))
    d = out[2025]
    assert d["p10"] == pytest.approx(combos[0]) and d["p90"] == pytest.approx(combos[-1]) and d["p50"] == pytest.approx(float(np.median(combos)))


def test_a_season_with_a_missing_day_in_any_source_is_left_out_not_filled():
    rain, et0 = daily("2024-01-01", "2025-12-31", 0.0, "r"), daily("2024-01-01", "2025-12-31", 4.0, "e")
    rain.columns["r"][np.where(rain.dates == np.datetime64("2025-03-10"))[0][0]] = np.nan
    assert season.flowering_deficits("december", 1.2, [(rain, "r")], [(et0, "e")]) == {}


def test_the_deficit_never_goes_below_zero_when_it_rains_more_than_the_crop_needs():
    out = season.flowering_deficits("december", 1.2, [(daily("2024-01-01", "2025-12-31", 20.0, "r"), "r")], [(daily("2024-01-01", "2025-12-31", 1.0, "e"), "e")])
    assert out[2025] == {"p10": 0.0, "p50": 0.0, "p90": 0.0}


def test_the_seasons_carry_heat_days_for_the_same_flowering_year():
    power = daily("2024-01-01", "2025-12-31", 30.0, "T2M_MAX")
    hot = (power.dates >= np.datetime64("2025-03-01")) & (power.dates <= np.datetime64("2025-03-03"))
    power.columns["T2M_MAX"][hot] = 36.0
    rain, et0 = daily("2024-01-01", "2025-12-31", 0.0, "r"), daily("2024-01-01", "2025-12-31", 4.0, "e")
    rows = season.seasons_part("december", 1.2, [(rain, "r")], [(et0, "e")], power)
    assert rows == [{"year": 2025, "deficit": {"p10": 254.4, "p50": 254.4, "p90": 254.4}, "heat_days": 3}]


def test_rain_this_season_accumulates_by_month_and_projects_with_the_other_years():
    # 1 mm cada día: años completos de 2020 a 2023 y el 2024 solo hasta marzo
    full = daily("2020-01-01", "2023-12-31", 1.0, "precip_mm_day")
    part = daily("2024-01-01", "2024-03-31", 1.0, "precip_mm_day")
    series = Series(np.concatenate([full.dates, part.dates]), {"precip_mm_day": np.concatenate([full.col("precip_mm_day"), part.col("precip_mm_day")])})
    out = season.rain_this_season_part(series)
    assert out["observed"] == [31.0, 60.0, 91.0]  # 2024 es bisiesto
    assert len(out["projected"]) == 9 and out["projected"][0] == {"y": 121.0, "lo": 121.0, "hi": 121.0}
    assert season.rain_this_season_part(Series(np.array([np.datetime64("2024-01-05")]), {"precip_mm_day": np.array([1.0])})) is None


def test_the_normals_and_thresholds_are_computed_from_the_years_and_say_which_ones():
    years = [2016, 2017, 2018, 2019]
    dates = np.concatenate([np.arange(np.datetime64(f"{y}-01-01"), np.datetime64(f"{y}-12-31") + np.timedelta64(1, "D")) for y in years])
    imerg = Series(dates, {"precip_mm_day": np.full(len(dates), 2.0)})
    power = Series(dates, {"T2M_MAX": np.full(len(dates), 39.0)})
    n = season.normals_part(imerg, power)
    assert n["rain"] == {"p10": 368.0, "p90": 368.0, "unit": "mm", "period": "2016–2019", "source": "GPM IMERG"}
    assert n["heat"] == {"p10": 39.0, "p90": 39.0, "unit": "°C", "period": "2016–2019", "source": "NASA POWER"}
    rows = [{"year": 2020 + i, "deficit": {"p10": 0, "p50": v, "p90": 0}, "heat_days": 0} for i, v in enumerate([100.0, 200.0, 300.0, 400.0])]
    assert season.thresholds_part(rows) == {"deficit_mm": 325.0, "heat_c": 35.0}
    assert season.thresholds_part(rows[:2]) is None  # con menos de tres temporadas no hay umbral
