"""SMAP L4 sin red: la malla EASE-Grid se estima con la fórmula y se comprueba contra el archivo."""

import json
import re

import numpy as np
import pytest

from harmonize import values
from ingest import smap
from ingest.contract import Fetch, Provenance, Series, SourceError
from ingest.http import Client

TOKEN = "tokenfalso." + "z" * 40
OPENDAP = "https://opendap.earthdata.nasa.gov/collections/C3480440870-NSIDC_CPRD/granules/{title}"


def lat_of(row):  # la malla real cerca del punto: la fila 530 es 20.2876° y cada fila baja 0.0751°
    return 20.2876 - 0.0751 * (row - 530)


def lon_of(col):  # la columna 970 es -89.3932° y cada columna sube 0.0933°
    return -89.3932 + 0.0933 * (col - 970)


def entry(day: str, hhmm: str, rev: str = "Vv8012") -> dict:
    title = f"SMAP_L4_SM_gph_{day.replace('-', '')}T{hhmm}_{rev}_001.h5_xx"
    return {"title": title, "links": [{"rel": "http://esipfed.org/ns/fedsearch/1.1/service#", "href": OPENDAP.format(title=title)}]}


def cmr_transport(entries):
    def transport(method, url, headers, body, timeout):
        page, size = int(re.search(r"page_num=(\d+)", url).group(1)), int(re.search(r"page_size=(\d+)", url).group(1))
        return 200, json.dumps({"feed": {"entry": entries[(page - 1) * size : page * size]}}).encode(), url

    return transport


def window_csv(var: str, rows, cols, fn) -> str:
    lines = [f"/{var}[{i}], " + ", ".join(f"{fn(r, c)}" for c in cols) for i, r in enumerate(rows)]
    return "Dataset: SMAP_L4_SM_gph_x.h5\n" + "\n".join(lines) + "\n"


def opendap_once(seen, *, shift=0, fail=(), fail_data=(), root=lambda day: 0.17, surf=lambda day: 0.10):
    """Un `once` falso que contesta cell_lat, cell_lon, sm_rootzone y sm_surface con la forma real del servidor."""
    def once(url, headers, timeout):
        seen.append((url, dict(headers)))
        day = re.search(r"gph_(\d{8})T", url).group(1)
        if day in fail or (day in fail_data and "sm_" in url):
            return 500, {}, b""
        ce = re.search(r"dap4\.ce=(.*)$", url).group(1).replace("%5B", "[").replace("%5D", "]").replace("%3A", ":").replace("%3B", ";")
        out = ""
        for var, r0, r1, c0, c1 in re.findall(r"/([\w/]+)\[(\d+):(\d+)\]\[(\d+):(\d+)\]", ce):
            rows, cols = range(int(r0), int(r1) + 1), range(int(c0), int(c1) + 1)
            fn = {"cell_lat": lambda r, c: round(lat_of(r + shift), 4), "cell_lon": lambda r, c: round(lon_of(c + shift), 4),
                  "Geophysical_Data/sm_rootzone": lambda r, c: root(day), "Geophysical_Data/sm_surface": lambda r, c: surf(day)}[var]
            out += window_csv(var, rows, cols, fn).split("\n", 1)[1]
        return 200, {}, ("Dataset: x\n" + out).encode()

    return once


def make_client(entries, once):
    c = Client(transport=cmr_transport(entries), sleep=lambda s: None, jitter=lambda: 0)
    c.once = once
    return c


# ---- La malla ------------------------------------------------------------------------------------------------------

def test_the_grid_estimate_lands_next_to_the_cell_the_file_confirms():
    row, col = smap.ease_estimate(-89.42, 20.30)
    assert (round(row), round(col)) == (530, 970) and abs(row - 529.83) < 0.01 and abs(col - 969.71) < 0.01


def test_the_cell_is_the_nearest_one_the_file_itself_reports():
    c = Client(sleep=lambda s: None)
    c.once = opendap_once([])
    cell = smap.locate_cell(c, TOKEN, "https://opendap.earthdata.nasa.gov/collections/C/granules/gph_20250601T163000_x", -89.42, 20.30)
    assert (cell["row"], cell["col"], cell["lat_center"], cell["lon_center"]) == (530, 970, 20.2876, -89.3932) and cell["distance_km"] == pytest.approx(3.1, abs=0.2)


def test_a_wrong_grid_estimate_is_refused_instead_of_picking_a_wrong_cell():
    c = Client(sleep=lambda s: None)
    c.once = opendap_once([], shift=40)  # el archivo dice que esas celdas están a ~300 km
    with pytest.raises(SourceError, match="la estimación de la malla falló"):
        smap.locate_cell(c, TOKEN, "https://opendap.earthdata.nasa.gov/collections/C/granules/gph_20250601T163000_x", -89.42, 20.30)


def test_the_request_encodes_brackets_and_colons_and_asks_for_two_by_two_cells():
    url = smap.ce_url("https://opendap.earthdata.nasa.gov/collections/C/granules/G", "/Geophysical_Data/sm_rootzone[530:531][970:971]")
    assert "[" not in url and "]" not in url and "%5B530%3A531%5D%5B970%3A971%5D" in url


# ---- Leer el CSV ---------------------------------------------------------------------------------------------------

def test_a_window_is_parsed_and_the_fill_value_becomes_nan():
    g = smap.parse_window("Dataset: x\n/Geophysical_Data/sm_rootzone[0], 0.17, -9999.0\n/Geophysical_Data/sm_rootzone[1], 0.18, 0.19\n", "Geophysical_Data/sm_rootzone")
    assert g.shape == (2, 2) and g[0, 0] == 0.17 and np.isnan(g[0, 1]) and g[1, 1] == 0.19


def test_error_answers_and_missing_variables_are_errors():
    with pytest.raises(SourceError, match="no válido"):
        smap.parse_window('Dataset: ERROR\r\nstatus, 400\r\nmessage, "no válido"\r\n', "cell_lat")
    with pytest.raises(SourceError, match="no devolvió cell_lat"):
        smap.parse_window("Dataset: x\n/cell_lon[0], 1\n", "cell_lat")
    with pytest.raises(SourceError, match="no es número"):
        smap.parse_window("Dataset: x\n/cell_lat[0], abc\n", "cell_lat")


# ---- Los granulos --------------------------------------------------------------------------------------------------

def test_only_the_granule_of_the_chosen_hour_is_used_and_a_reprocess_of_the_same_instant_wins():
    entries = [entry("2025-06-01", h) for h in ("013000", "163000", "223000")] + [entry("2025-06-01", "163000", rev="Vv8013"), entry("2025-06-02", "163000")]
    g = smap.list_granules(make_client(entries, None), "2025-06-01", "2025-06-02")
    assert sorted(g) == ["2025-06-01", "2025-06-02"] and "Vv8013" in g["2025-06-01"] and all("T163000" in u for u in g.values())


# ---- La serie ------------------------------------------------------------------------------------------------------

DAYS = ["2025-06-01", "2025-06-02", "2025-06-03", "2025-06-05"]  # el 4 no tiene granulo
ENTRIES = [entry(d, h) for d in DAYS for h in ("013000", "163000", "223000")]


def run_fetch(fail=(), fail_data=(), entries=ENTRIES, **kw):
    seen = []
    c = make_client(entries, opendap_once(seen, fail=fail, fail_data=fail_data, root=lambda d: {"20250601": 0.17, "20250602": 0.18, "20250603": 0.21, "20250605": 0.2}[d], surf=lambda d: 0.1))
    return smap.fetch_smap(c, -89.42, 20.30, "2025-06-01", "2025-06-05", token=TOKEN, **kw), seen


def test_the_series_has_one_value_per_day_and_missing_days_stay_empty():
    f, _ = run_fetch()
    assert [str(d) for d in f.data.dates] == ["2025-06-01", "2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05"]
    assert np.allclose(f.data.col("sm_rootzone"), [0.17, 0.18, 0.21, np.nan, 0.2], equal_nan=True)
    assert f.units["sm_rootzone"] == "m3/m3" and f.prov.params["cell"]["row"] == 530 and f.prov.params["hhmm_utc"] == "16:30"
    assert any("1 días sin granulo" in n for n in f.notes) and any("3.1 km del punto" in n for n in f.notes)


def test_a_failed_day_is_reported_and_all_failing_is_no_data():
    f, _ = run_fetch(fail=("20250603",))
    assert np.isnan(f.data.col("sm_rootzone")[2]) and any("1 días sin respuesta" in n for n in f.notes)
    every = ("20250601", "20250602", "20250603", "20250605")
    with pytest.raises(SourceError, match="ningún día de SMAP respondió"):
        run_fetch(fail_data=every)  # la celda se ubica, pero ningún día entrega humedad
    with pytest.raises(SourceError, match="HTTP 500"):
        run_fetch(fail=every)  # ni siquiera se puede ubicar la celda


def test_every_request_carries_the_token_in_the_header_only():
    f, seen = run_fetch()
    assert seen and all(h["Authorization"] == f"Bearer {TOKEN}" for _, h in seen) and all(TOKEN not in u for u, _ in seen)
    assert TOKEN not in json.dumps({"n": f.notes, "p": f.prov.__dict__}, default=str)


def test_without_granules_the_source_is_no_data():
    with pytest.raises(SourceError, match="no tiene granulos"):
        run_fetch(entries=[])


# ---- El valor del contrato -----------------------------------------------------------------------------------------

def smap_fetch(root: np.ndarray) -> Fetch:
    d = np.arange(np.datetime64("2025-01-01"), np.datetime64("2025-01-01") + np.timedelta64(len(root), "D"), dtype="datetime64[D]")
    prov = Provenance("SMAP L4 (NASA NSIDC DAAC)", "SPL4SMGP v008", "x", {"cell": {"lon_center": -89.3932, "lat_center": 20.2876}, "hhmm_utc": "16:30"}, response_sha256="ab" * 32)
    return Fetch(Series(d, {"sm_rootzone": root, "sm_surface": root * 0.5}), prov)


def test_the_moisture_value_is_context_of_the_zone_with_the_range_between_days():
    v = values.moisture_value(smap_fetch(np.linspace(0.10, 0.30, 365)))
    assert (v["variable"], v["unit"], v["support_level"], v["method"], v["assumptions"], v["timestamp"]) == ("soil_moisture_rootzone", "m³/m³", "zone", "modeled", ["contextOnly"], "2025-12")
    assert v["value"] == pytest.approx(0.20, abs=0.001) and v["p10"] < v["value"] < v["p90"]
    assert any("365 días" in s for s in v["provenance"]) and any("-89.3932, 20.2876" in s for s in v["provenance"])


def test_with_too_few_days_the_moisture_is_declared_without_data():
    sparse = np.full(365, np.nan)
    sparse[:100] = 0.2  # 27 % de los días: menos del 80 %
    v = values.moisture_value(smap_fetch(sparse))
    assert (v["value"], v["p10"], v["p90"]) == (None, None, None) and "al menos el 80%" in " ".join(v["provenance"])
