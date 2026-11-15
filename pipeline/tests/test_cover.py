"""De las observaciones de NDVI a los meses con o sin plantas verdes y a los días del año sin ellas."""

from datetime import date

import numpy as np
import pytest

from harmonize.cover import GREEN_NDVI_MIN, bare_days, bare_value, green_cover_json, monthly_classes
from ingest.contract import Fetch, Provenance
from ingest.vegetation import Observation


def o(y, m, ndvi, d=10, sensor="HLS-L30"):
    return Observation(date(y, m, d), sensor, f"{y}-{m}-{d}", ndvi, 12, 12 if np.isfinite(ndvi) else 0)


def fetch(observations, start="2016-01-01", end="2025-12-31"):
    return Fetch(observations, Provenance("HLS (NASA LP DAAC)", "p", "e", {"start": start, "end": end}, requested_at="2026-11-15T00:00:00Z"))


def year_obs(y, letters):
    """Una observación por mes con la clase pedida (C, B o N)."""
    return [o(y, m, {"C": 0.6, "B": 0.2, "N": float("nan")}[ch]) for m, ch in enumerate(letters, 1)]


def test_each_month_takes_the_median_of_its_clear_scenes_against_the_threshold():
    obs = [o(2020, 1, 0.20), o(2020, 1, 0.50, d=20), o(2020, 1, 0.60, d=25),   # mediana 0.50: con plantas
           o(2020, 2, 0.34), o(2020, 3, 0.35), o(2020, 4, float("nan"))]        # justo por debajo, justo en el umbral, sin dato
    c = monthly_classes(obs, 2020, 2020)[2020]
    assert c[:4] == "CBCN" and len(c) == 12 and set(c[4:]) == {"N"}


def test_a_cloudy_scene_does_not_make_a_month_bare_and_years_without_scenes_are_all_unknown():
    c = monthly_classes([o(2021, 5, float("nan"))], 2020, 2021)
    assert c == {2020: "N" * 12, 2021: "N" * 12}


def test_unknown_months_are_not_counted_as_bare_and_a_year_needs_nine_known_months():
    classes = {2020: "BBBNNNCCCCCC", 2021: "BBBBNNNNNCCC", 2022: "BBBBBBBBBBBB"}
    assert bare_days(classes) == {2020: 31 + 29 + 31, 2022: 365}  # 2021 tiene 5 meses sin dato: no cuenta


def test_leap_years_count_february_29():
    assert bare_days({2020: "NBCCCCCCCCCC", 2021: "NBCCCCCCCCCC"}) == {2020: 29, 2021: 28}


def test_the_value_is_the_median_and_range_across_years_as_a_minimum_with_its_assumptions():
    obs = []
    for y, letters in {2016: "BBBCCCCCCCCC", 2017: "BBBBCCCCCCCC", 2018: "BBBBBCCCCCCC", 2019: "BBBBBBCCCCCC"}.items():
        obs += year_obs(y, letters)
    v = bare_value(fetch(obs))
    days = [31 + 29 + 31, 31 + 28 + 31 + 30, 31 + 28 + 31 + 30 + 31, 31 + 28 + 31 + 30 + 31 + 30]
    assert v["variable"] == "days_without_green_cover" and v["unit"] == "days" and v["method"] == "measured" and v["support_level"] == "parcel"
    assert v["value"] == pytest.approx(np.median(days)) and v["p10"] == pytest.approx(np.percentile(days, 10)) and v["p90"] == pytest.approx(np.percentile(days, 90))
    assert set(v["assumptions"]) == {"innerBuffer", "greenNotStubble"} and v["native_resolution"] == "30 m"
    assert any("mínimo" in s for s in v["provenance"]) and any("4 años" in s for s in v["provenance"])


def test_fewer_than_three_qualifying_years_is_no_data_not_a_guess():
    obs = year_obs(2016, "BBBCCCCCCCCC") + year_obs(2017, "BBBBCCCCCCCC") + year_obs(2018, "BBBBNNNNNCCC")  # 2018 solo tiene 7 meses con dato
    v = bare_value(fetch(obs))
    assert v["value"] is None and v["p10"] is None and v["p90"] is None
    assert any("sin dato: 2 años" in s for s in v["provenance"])


def test_no_clear_scene_at_all_is_no_data():
    assert bare_value(fetch([o(2020, 1, float("nan"))]))["value"] is None


def test_the_sentinel_2_backup_is_declared_in_the_provenance():
    obs = []
    for y in (2016, 2017, 2018):
        obs += year_obs(y, "BBBCCCCCCCCC")
    obs.append(o(2018, 12, 0.5, sensor="S2"))
    v = bare_value(fetch(obs))
    assert any("Sentinel-2 (respaldo)" in s for s in v["provenance"])


def test_the_timestamp_is_the_month_of_the_last_clear_observation():
    obs = []
    for y in (2016, 2017, 2018):
        obs += year_obs(y, "BBBCCCCCCCCC")
    assert bare_value(fetch(obs))["timestamp"] == "2018-12"


def test_the_gold_file_lists_every_year_with_its_twelve_letters():
    g = green_cover_json(fetch(year_obs(2016, "BBBCCCCCCCCC"), start="2016-01-01", end="2017-12-31"))
    assert g["years"] == {"2016": "BBBCCCCCCCCC", "2017": "N" * 12} and "0.35" in g["source"] and "N = sin dato" in g["_codigo"]
    assert GREEN_NDVI_MIN == 0.35


def test_the_ndvi_source_asks_for_the_scene_list_first_and_never_without_a_token(monkeypatch):
    from ingest import load
    from ingest.http import Client

    c = Client(sleep=lambda s: None)
    p = load.Params(-89.42, 20.30, "2025-01-01", "2025-01-31")
    assert load.run_one(c, "hls_ndvi", p).status == load.STATUS_PENDING  # sin hls_stac no hay qué leer
    scenes = Fetch([], Provenance("s", "p", "e", {}))
    assert load.run_one(c, "hls_ndvi", p, {"hls_stac": load.Result("hls_stac", load.STATUS_OK, "", scenes)}).status == load.STATUS_PENDING  # sin token: «falta …», no un error
