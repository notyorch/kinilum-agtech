"""SoilGrids sin valores en el punto: nunca se convierte un nulo en número y el respaldo es explícito."""

import json
import re
from pathlib import Path

import pytest

from harmonize import values
from ingest import load, soilgrids
from ingest.contract import Fetch, Provenance, SourceError
from ingest.http import Client
from ingest.load import Result

FIXTURES = Path(__file__).parent / "fixtures"
POINT = (-89.42, 20.30)


def fx(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def soil_client(valid, seen, sleeps):
    """`valid(lon, lat)` dice si ese punto tiene valores; si no, responde con la celda toda nula (como el servicio real)."""
    def transport(method, url, headers, body, timeout):
        lon, lat = float(re.search(r"lon=([-\d.]+)", url).group(1)), float(re.search(r"lat=([-\d.]+)", url).group(1))
        seen.append((lon, lat, url))
        return 200, json.dumps(fx("soilgrids_values.json" if valid(lon, lat) else "soilgrids_null.json")).encode(), url

    return Client(transport=transport, sleep=lambda s: None, jitter=lambda: 0)


PROPS = dict(properties=("clay", "soc"), depths=("0-5cm", "15-30cm"))


def test_the_point_with_values_needs_no_fallback_and_no_waiting():
    seen, sleeps = [], []
    f = soilgrids.fetch_soilgrids_nearest(soil_client(lambda lo, la: True, seen, sleeps), *POINT, **PROPS, sleep=sleeps.append)
    assert len(seen) == 1 and sleeps == [] and "fallback" not in f.prov.params and not any("celda válida más cercana" in n for n in f.notes)


def test_the_nearest_valid_cell_is_found_ring_by_ring_and_says_how_far_and_which_way():
    ring = list(soilgrids.ring_points(*POINT))
    target = next((lo, la) for r, name, lo, la in ring if (r, name) == (500, "norte"))
    seen, sleeps = [], []
    f = soilgrids.fetch_soilgrids_nearest(soil_client(lambda lo, la: abs(lo - target[0]) < 1e-9 and abs(la - target[1]) < 1e-9, seen, sleeps), *POINT, **PROPS, sleep=sleeps.append)
    assert f.prov.params["fallback"] == {"distance_m": 500, "direction": "norte", "lon": target[0], "lat": target[1]}
    assert f.notes[0] == "El punto no tiene valores: se usó la celda válida más cercana, a 500 m al norte"
    # 1 consulta del punto + 8 del anillo de 250 m + el sondeo del norte a 500 m + la consulta completa
    assert len(seen) == 11
    assert seen[-1][2].count("property=") == 2 and seen[-2][2].count("property=") == 1  # el sondeo pide una sola capa
    assert len(sleeps) == 10 and set(sleeps) == {soilgrids.PAUSE_S}  # SoilGrids limita las consultas: se espera entre una y otra


def test_the_nearest_candidate_wins_over_a_farther_one():
    seen, sleeps = [], []
    f = soilgrids.fetch_soilgrids_nearest(soil_client(lambda lo, la: abs(la - POINT[1]) > 1e-9 or abs(lo - POINT[0]) > 1e-9, seen, sleeps), *POINT, **PROPS, sleep=sleeps.append)
    assert (f.prov.params["fallback"]["distance_m"], f.prov.params["fallback"]["direction"]) == (250, "norte")  # el primero del anillo más cercano


def test_if_no_cell_around_has_values_the_source_is_no_data_and_nothing_is_invented():
    seen, sleeps = [], []
    with pytest.raises(SourceError, match="ni a 1000 m a la redonda"):
        soilgrids.fetch_soilgrids_nearest(soil_client(lambda lo, la: False, seen, sleeps), *POINT, **PROPS, sleep=sleeps.append)
    assert len(seen) == 1 + 24  # el punto y los tres anillos, sin consulta completa


def test_the_search_radius_can_be_limited():
    seen, sleeps = [], []
    with pytest.raises(SourceError, match="ni a 250 m"):
        soilgrids.fetch_soilgrids_nearest(soil_client(lambda lo, la: False, seen, sleeps), *POINT, **PROPS, radii=(250,), sleep=sleeps.append)
    assert len(seen) == 1 + 8


def test_the_loader_turns_the_fallback_off_with_zero_and_limits_the_rings(monkeypatch):
    asked = {}
    monkeypatch.setattr(soilgrids, "fetch_soilgrids_nearest", lambda c, lon, lat, radii=(), **k: asked.setdefault("radii", radii) or Fetch([], Provenance("s", "p", "e", {})))
    monkeypatch.setattr(soilgrids, "fetch_soilgrids", lambda c, lon, lat, *a, **k: asked.setdefault("plain", True) and Fetch([], Provenance("s", "p", "e", {})))
    client = Client(sleep=lambda s: None)
    load.soil_connector(client, load.Params(*POINT, "2016-01-01", "2016-01-02", soil_fallback_m=500))
    assert asked["radii"] == (250, 500)
    load.soil_connector(client, load.Params(*POINT, "2016-01-01", "2016-01-02", soil_fallback_m=0))
    assert asked["plain"] is True


# ---- El valor del contrato: el bug E8 ------------------------------------------------------------------------------

def rows(mean, q05, q95):
    return [{"property": "clay", "depth": "0-5cm", "units": "%", "mean": mean, "q05": q05, "q95": q95}]


def soil_fetch(data, fallback=None):
    params = {"fallback": fallback} if fallback else {}
    return Fetch(data, Provenance("SoilGrids (ISRIC)", "properties/query v2.0", "x", params, response_sha256="ab" * 32))


def test_a_null_layer_is_declared_without_data_instead_of_crashing_in_float():
    """El error E8: el notebook hacía float(None) con la arcilla nula. Aquí un nulo nunca se convierte."""
    v = values.clay_value(soil_fetch(rows(None, None, None)))
    assert (v["value"], v["p10"], v["p90"]) == (None, None, None) and v["variable"] == "clay_0_5cm"
    assert "sin dato" in " ".join(v["provenance"])


def test_a_mean_without_quantiles_is_not_half_a_value():
    v = values.clay_value(soil_fetch(rows(25.0, None, 31.0)))
    assert (v["value"], v["p10"], v["p90"]) == (None, None, None)


def test_a_valid_layer_gives_the_mean_with_the_quantile_5_to_95_range():
    v = values.clay_value(soil_fetch(rows(25.0, 20.0, 31.0)))
    assert (v["value"], v["p10"], v["p90"], v["unit"], v["support_level"], v["method"]) == (25.0, 20.0, 31.0, "%", "surroundings", "modeled")
    assert "rango = cuantiles 5 y 95, no 10 y 90" in v["provenance"]


def test_a_neighbour_cell_is_marked_interpolated_and_says_how_far():
    v = values.clay_value(soil_fetch(rows(25.0, 20.0, 31.0), {"distance_m": 500, "direction": "norte"}))
    assert v["method"] == "interpolated" and any("a 500 m al norte" in s for s in v["provenance"])


def test_a_source_that_never_arrived_still_appears_as_without_data():
    ctx = values.context_values({"soilgrids": Result("soilgrids", "no_data", "SoilGrids no tiene valores en este punto")})
    v = ctx["clay_0_5cm"]
    assert (v["value"], v["p10"], v["p90"]) == (None, None, None) and "SoilGrids no tiene valores" in " ".join(v["provenance"])
    assert values.context_values({}) == {}


def test_the_loader_uses_the_clients_pause_so_that_nothing_really_waits():
    seen, sleeps = [], []
    c = soil_client(lambda lo, la: False, seen, sleeps)
    c.sleep = sleeps.append
    r = load.run_one(c, "soilgrids", load.Params(*POINT, "2016-01-01", "2016-01-02", soil_fallback_m=250))
    assert r.status == "no_data" and "ni a 250 m" in r.detail and len(sleeps) == 8 and set(sleeps) == {soilgrids.PAUSE_S}
