"""IMERG y NASADEM sin red: respuestas con la forma real de cada servicio y un transporte autenticado falso."""

import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
import pytest

from ingest import imerg, nasadem
from ingest.contract import SourceError
from ingest.http import Client

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "tokenfalso." + "y" * 40
OPENDAP = "https://opendap.earthdata.nasa.gov/collections/C2723754864-GES_DISC/granules/GPM_3IMERGDF.07%3A3B-DAY.MS.MRG.3IMERG.{d}-S000000-E235959.V07B.nc4"


def fx(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def granule_entry(day: str) -> dict:
    d = day.replace("-", "")
    return {"title": f"GPM_3IMERGDF.07:3B-DAY.MS.MRG.3IMERG.{d}-S000000-E235959.V07B.nc4",
            "links": [{"rel": "http://esipfed.org/ns/fedsearch/1.1/service#", "href": OPENDAP.format(d=d)},
                      {"rel": "http://esipfed.org/ns/fedsearch/1.1/data#", "href": "https://data.gesdisc.earthdata.nasa.gov/data/x.nc4"}]}


def cmr_transport(days, seen=None):
    def transport(method, url, headers, body, timeout):
        if seen is not None:
            seen.append(url)
        page = int(re.search(r"page_num=(\d+)", url).group(1))
        size = int(re.search(r"page_size=(\d+)", url).group(1))
        chunk = days[(page - 1) * size : page * size]
        return 200, json.dumps({"feed": {"entry": [granule_entry(d) for d in chunk]}}).encode(), url

    return transport


def csv_for(a, b) -> bytes:
    return f"Dataset: 3B-DAY.MS.MRG.3IMERG.x.nc4\n/precipitation[0][0], {a}, {b}\n".encode()


def opendap_once(values, seen, fail=()):
    """Un `once` falso: {AAAAMMDD: (celda, vecina)}; `fail` son días que responden 500."""
    def once(url, headers, timeout):
        seen.append((url, dict(headers)))
        day = re.search(r"3IMERG\.(\d{8})-S", url).group(1)
        if day in fail:
            return 500, {}, b""
        a, b = values[day]
        return 200, {}, csv_for(a, b)

    return once


def make_client(days, once, seen=None):
    c = Client(transport=cmr_transport(days, seen), sleep=lambda s: None, jitter=lambda: 0)
    c.once = once
    return c


# ---- IMERG: la celda -----------------------------------------------------------------------------------------------

def test_the_example_point_sits_exactly_on_a_cell_edge_and_goes_to_the_cell_that_contains_it():
    c = imerg.cell_index(-89.42, 20.30)
    assert (c["lon_index"], c["lat_index"], c["lon_center"], c["lat_center"]) == (905, 1103, -89.45, 20.35)
    assert c["margin_deg"] == 0.0 and c["pair"] == (1102, 1103) and c["pos"] == 1  # el borde es con la celda del sur


def test_the_neighbour_is_on_the_side_of_the_nearest_edge():
    south = imerg.cell_index(-89.42, 20.33)
    north = imerg.cell_index(-89.42, 20.37)
    # El margen es la distancia al borde MÁS cercano: aquí el borde este (0.02°) y no el de latitud (0.03°).
    assert (south["pair"], south["pos"], south["margin_deg"]) == ((1102, 1103), 1, 0.02)
    assert (north["pair"], north["pos"], north["margin_deg"]) == ((1103, 1104), 0, 0.02)


@pytest.mark.parametrize("lon,lat", [(-89.42, 89.99), (-89.42, -89.99), (-181.0, 20.3)])
def test_points_outside_the_grid_are_refused(lon, lat):
    with pytest.raises(SourceError, match="fuera de la malla"):
        imerg.cell_index(lon, lat)


def test_the_opendap_request_has_encoded_brackets_because_raw_ones_get_a_400():
    url = imerg.dap_url("https://opendap.earthdata.nasa.gov/collections/C/granules/G", 905, 1102, 1103)
    assert "[" not in url and "]" not in url and "precipitation%5B0%3A0%5D%5B905%3A905%5D%5B1102%3A1103%5D" in url
    assert url.endswith("1103%5D") and ".dap.csv?dap4.ce=" in url


# ---- IMERG: leer el CSV --------------------------------------------------------------------------------------------

def test_the_csv_of_two_cells_is_parsed_and_the_fill_value_becomes_none():
    assert imerg.parse_point_csv(csv_for(0.35, 0.99).decode()) == [0.35, 0.99]
    assert imerg.parse_point_csv(csv_for(-9999.9, 4.5).decode()) == [None, 4.5]


def test_the_empty_csv_of_a_single_cell_is_an_error_not_a_zero():
    """OPeNDAP devuelve vacío cuando se pide UNA sola celda: eso no es «cero milímetros»."""
    with pytest.raises(SourceError, match="0 valores"):
        imerg.parse_point_csv("Dataset: x\n/precipitation[0][0], \n")


def test_error_answers_and_garbage_are_errors():
    with pytest.raises(SourceError, match="expresión no válida"):
        imerg.parse_point_csv('Dataset: ERROR\r\nstatus, 400\r\nmessage, "expresión no válida"\r\n')
    with pytest.raises(SourceError, match="no devolvió la variable"):
        imerg.parse_point_csv("Dataset: x\n/lon, -89.5\n")
    with pytest.raises(SourceError, match="no es número"):
        imerg.parse_point_csv("Dataset: x\n/precipitation[0][0], abc, 1\n")


# ---- IMERG: los granulos de CMR ------------------------------------------------------------------------------------

def test_granules_map_each_day_to_its_opendap_link():
    c = make_client(["2025-06-01", "2025-06-02"], None)
    g = imerg.list_granules(c, "2025-06-01", "2025-06-02")
    assert list(g) == ["2025-06-01", "2025-06-02"] and g["2025-06-01"].startswith("https://opendap.earthdata.nasa.gov/collections/")


def test_granules_are_read_page_by_page(monkeypatch):
    monkeypatch.setattr(imerg, "PAGE_SIZE", 2)
    seen = []
    days = [f"2025-06-0{d}" for d in range(1, 6)]
    g = imerg.list_granules(make_client(days, None, seen), "2025-06-01", "2025-06-05")
    assert sorted(g) == days and len(seen) == 3  # 2 + 2 + 1


# ---- IMERG: la serie -----------------------------------------------------------------------------------------------

DAYS = ["2025-06-01", "2025-06-02", "2025-06-03", "2025-06-05"]  # el 4 no tiene granulo
# (valor en el índice de latitud menor, valor en el mayor). El punto de ejemplo es la SEGUNDA celda de la pareja
# (la primera es su vecina del sur), así que la celda del punto es el segundo número.
VALUES = {"20250601": (0.9, 0.5), "20250602": (2.0, -9999.9), "20250603": (7.0, 20.0), "20250605": (1.5, 1.0)}


def run_fetch(days=DAYS, fail=(), workers=4, values=VALUES):
    seen = []
    c = make_client(days, opendap_once(values, seen, fail))
    return imerg.fetch_imerg(c, -89.42, 20.30, "2025-06-01", "2025-06-05", token=TOKEN, workers=workers), seen


def test_the_series_puts_each_value_on_its_day_and_keeps_the_neighbour():
    f, _ = run_fetch()
    s = f.data
    assert [str(d) for d in s.dates] == ["2025-06-01", "2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05"]
    assert np.allclose(s.col("precip_mm_day"), [0.5, np.nan, 20.0, np.nan, 1.0], equal_nan=True)
    assert np.allclose(s.col("neighbor_mm_day"), [0.9, 2.0, 7.0, np.nan, 1.5], equal_nan=True)
    assert f.units["precip_mm_day"] == "mm/day" and f.prov.source.startswith("GPM IMERG") and len(f.prov.response_sha256) == 64


def test_missing_days_failed_days_and_the_cell_edge_are_all_reported():
    f, _ = run_fetch(fail=("20250603",))
    notes = " | ".join(f.notes)
    assert "1 días sin granulo" in notes and "llega hasta 2025-06-05" in notes
    assert "1 días sin respuesta" in notes and "borde de la celda" in notes
    assert np.isnan(f.data.col("precip_mm_day")[2])  # el día que falló queda sin dato, no en cero


def test_every_request_carries_the_token_in_the_header_and_never_in_the_url():
    f, seen = run_fetch()
    assert len(seen) == 4 and all(h["Authorization"] == f"Bearer {TOKEN}" for _, h in seen)
    assert all(TOKEN not in url for url, _ in seen)
    assert TOKEN not in json.dumps({"notes": f.notes, "prov": f.prov.__dict__}, default=str)


def test_the_result_does_not_depend_on_how_many_threads_ask():
    one, _ = run_fetch(workers=1)
    many, _ = run_fetch(workers=4)
    assert np.allclose(one.data.col("precip_mm_day"), many.data.col("precip_mm_day"), equal_nan=True)
    assert one.prov.response_sha256 == many.prov.response_sha256


def test_a_granule_outside_the_requested_period_is_neither_requested_nor_a_crash():
    values = {**VALUES, "20250701": (9.0, 9.0)}
    f, seen = run_fetch(days=[*DAYS, "2025-07-01"], values=values)
    assert len(f.data) == 5 and not any("20250701" in url for url, _ in seen) and len(seen) == 4


def test_if_no_day_answers_the_source_is_no_data():
    with pytest.raises(SourceError, match="ningún día de IMERG respondió"):
        run_fetch(fail=tuple(VALUES))


def test_without_granules_the_source_is_no_data():
    c = make_client([], None)
    with pytest.raises(SourceError, match="no tiene granulos"):
        imerg.fetch_imerg(c, -89.42, 20.30, "2025-06-01", "2025-06-05", token=TOKEN)


# ---- Cliente: descargas autenticadas -------------------------------------------------------------------------------

def test_authenticated_downloads_are_cached_and_the_token_never_reaches_the_cache(tmp_path):
    calls = []

    def once(url, headers, timeout):
        calls.append(headers.get("Authorization"))
        return 200, {}, b"hola"

    c = Client(tmp_path, sleep=lambda s: None)
    c.once = once
    first = c.get_authenticated("https://opendap.earthdata.nasa.gov/x", token=TOKEN)
    second = c.get_authenticated("https://opendap.earthdata.nasa.gov/x", token=TOKEN)
    assert (first.body, second.body, second.from_cache, len(calls)) == ("hola", "hola", True, 1)
    assert all(TOKEN not in p.read_text() for p in tmp_path.glob("*.json"))


def test_authenticated_errors_say_where_but_never_show_the_token():
    for status, expect in ((401, "sin acceso"), (403, "sin acceso"), (500, "HTTP 500")):
        c = Client(sleep=lambda s: None)
        c.once = lambda url, headers, timeout, s=status: (s, {}, b"")
        with pytest.raises(SourceError, match=expect) as e:
            c.get_authenticated("https://opendap.earthdata.nasa.gov/x?q=secreto-de-consulta", token=TOKEN)
        assert TOKEN not in str(e.value) and "secreto-de-consulta" not in str(e.value) and "opendap.earthdata.nasa.gov/x" in str(e.value)


def test_a_file_bigger_than_the_cap_is_an_error_not_a_truncated_file():
    c = Client(sleep=lambda s: None)
    c.once = lambda url, headers, timeout: (206, {"Content-Range": "bytes 0-9/5000"}, b"0" * 10)
    with pytest.raises(SourceError, match="pasa del tope"):
        c.get_authenticated("https://data.lpdaac.earthdatacloud.nasa.gov/f.zip", token=TOKEN, max_bytes=10, binary=True)


# ---- NASADEM -------------------------------------------------------------------------------------------------------

def plane(n, east_pct, south_pct, base=100.0, lat=20.3):
    """Un tile de n×n con pendiente conocida: `east_pct` % hacia el este y `south_pct` % hacia el sur."""
    res = 1.0 / (n - 1)
    dy, dx = nasadem.M_PER_DEG_LAT * res, nasadem.M_PER_DEG_LON_EQ * np.cos(np.radians(lat)) * res
    rows, cols = np.arange(n)[:, None], np.arange(n)[None, :]
    return np.rint(base + east_pct / 100 * dx * cols + south_pct / 100 * dy * rows).astype(">i2")


def test_the_slope_of_a_known_plane_is_recovered():
    t = nasadem.terrain(plane(3601, 50, 20), -89.42, 20.30)
    assert t["slope_pct"]["p50"] == pytest.approx(np.hypot(50, 20), abs=1.0)  # 53.9 %
    assert 9 <= t["clean_cells"] <= 16 and t["void_cells"] == 0


def test_a_flat_tile_has_no_slope_and_the_elevation_is_exact():
    flat = np.full((3601, 3601), 29, dtype=">i2")
    t = nasadem.terrain(flat, -89.42, 20.30)
    assert t["slope_pct"] == {"p10": 0.0, "p50": 0.0, "p90": 0.0}
    assert t["elevation_m"] == {"point": 29.0, "p10": 29.0, "p50": 29.0, "p90": 29.0}


def test_clean_pixels_are_fewer_than_the_tidy_formula_promises():
    """200 m con 30 m de borde son 140 m: la fórmula alineada da 16; con la cuadrícula real caben 9 a 16."""
    t = nasadem.terrain(np.full((3601, 3601), 29, dtype=">i2"), -89.42, 20.30)
    assert 9 <= t["clean_cells"] < 16 + 1 and t["sample_spacing_m"] == {"north_south": 30.7, "east_west": 29.0}


def test_voids_are_ignored_and_counted_and_an_all_void_parcel_is_no_data():
    tile = np.full((3601, 3601), 29, dtype=">i2")
    r0, c0 = round((21 - 20.30) * 3600), round(0.58 * 3600)
    tile[r0, c0] = nasadem.VOID
    t = nasadem.terrain(tile, -89.42, 20.30)
    assert t["void_cells"] == 1 and t["elevation_m"]["point"] is None and t["elevation_m"]["p50"] == 29.0
    tile[r0 - 5 : r0 + 6, c0 - 5 : c0 + 6] = nasadem.VOID
    with pytest.raises(SourceError, match="vacíos"):
        nasadem.terrain(tile, -89.42, 20.30)


def test_a_parcel_too_small_or_on_the_tile_edge_is_refused():
    flat = np.full((3601, 3601), 29, dtype=">i2")
    with pytest.raises(SourceError, match="ningún píxel completo"):
        nasadem.terrain(flat, -89.42, 20.30, side_m=60)
    with pytest.raises(SourceError, match="borde del tile"):
        nasadem.terrain(flat, -89.9995, 20.9995)


def test_tiles_are_named_the_way_nasa_names_them():
    assert nasadem.tile_name(-89.42, 20.30) == "NASADEM_HGT_n20w090"
    assert nasadem.tile_name(100.5, -3.2) == "NASADEM_HGT_s04e100"


def zipped(tile) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("n20w090.hgt", tile.tobytes())
        z.writestr("n20w090.num", b"\x00" * 16)
    return buf.getvalue()


def test_hgt_and_zip_errors_are_no_data():
    with pytest.raises(SourceError, match="no es una matriz cuadrada"):
        nasadem.read_hgt(b"\x00" * 1000)
    with pytest.raises(SourceError, match="no es un ZIP válido"):
        nasadem.hgt_from_zip(b"esto no es un zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("otra-cosa.txt", b"x")
    with pytest.raises(SourceError, match="no trae un archivo .hgt"):
        nasadem.hgt_from_zip(buf.getvalue())


def nasadem_client(zip_bytes, seen):
    body = json.loads((FIXTURES / "cmr_granule_nasadem.json").read_text(encoding="utf-8"))

    def transport(method, url, headers, payload, timeout):
        return 200, json.dumps(body).encode(), url

    def once(url, headers, timeout):
        seen.append((url, dict(headers)))
        return 206, {"Content-Range": f"bytes 0-{len(zip_bytes) - 1}/{len(zip_bytes)}"}, zip_bytes

    c = Client(transport=transport, sleep=lambda s: None, jitter=lambda: 0)
    c.once = once
    return c


def test_nasadem_downloads_the_tile_with_the_token_and_reads_the_point():
    seen = []
    c = nasadem_client(zipped(np.full((1201, 1201), 29, dtype=">i2")), seen)
    f = nasadem.fetch_nasadem(c, -89.42, 20.30, token=TOKEN)
    assert f.data["elevation_m"]["point"] == 29.0 and f.data["slope_pct"]["p50"] == 0.0
    assert f.prov.product == "NASADEM_HGT 001" and "doi:10.5067" in f.prov.citation
    assert seen[0][1]["Authorization"] == f"Bearer {TOKEN}" and TOKEN not in json.dumps({"n": f.notes, "p": f.prov.__dict__}, default=str)


def test_a_point_in_another_tile_than_the_one_cmr_returns_is_refused():
    c = nasadem_client(b"", [])
    with pytest.raises(SourceError, match="cruza dos tiles"):
        nasadem.fetch_nasadem(c, -90.5, 20.30, token=TOKEN)
