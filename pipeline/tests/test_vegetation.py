"""NDVI de la parcela por escena (HLS y Sentinel-2), con máscara de nubes, sobre archivos construidos en la prueba."""

import math
from datetime import date, datetime

import numpy as np
import pytest

from cogfile import build_cog, serve
from ingest import cover as cover_mod
from ingest.contract import Fetch, Provenance, SourceError
from ingest.geo import core_cells, utm_forward, utm_zone_of_epsg
from ingest.http import Client
from ingest.vegetation import Observation, hls_date, observe_hls, observe_many, observe_s2

LON, LAT = -89.42, 20.30
X, Y = utm_forward(LON, LAT, 16)
ROW, COL = 40.3, 50.4  # el punto cae aquí en la malla de cada archivo de prueba


def grid(pixel):
    """Origen y tamaño para que el punto caiga en la misma posición en metros con celdas de `pixel` m."""
    return (X - (COL * 30), Y + (ROW * 30)), (pixel, pixel)


def tif(arr, pixel=30.0, **kw):
    o, p = grid(pixel)
    return build_cog(arr, tile=16, origin=o, pixel=p, **kw)


def hls_scene(sid="HLS.L30.T16QBH.2025067T162223.v2.0", *, fmask, red, nir, nir_band="B05", extra=None):
    files = {"https://x/F.tif": tif(fmask.astype("u1"), nodata="255"), "https://x/R.tif": tif(red.astype("i2")), "https://x/N.tif": tif(nir.astype("i2"))}
    scene = {"id": sid, "assets": {"Fmask": {"href": "https://x/F.tif"}, "B04": {"href": "https://x/R.tif"}, nir_band: {"href": "https://x/N.tif"}}}
    return scene, files


def client_for(files):
    c = Client(sleep=lambda s: None)
    c.once = serve(files)
    return c


def full(value, shape=(100, 110), dtype="i2"):
    return np.full(shape, value, dtype=dtype)


def test_the_date_of_an_hls_scene_comes_from_its_identifier():
    assert hls_date("HLS.L30.T16QBH.2025067T162223.v2.0") == date(2025, 3, 8)
    assert hls_date("HLS.S30.T16QBH.2024366T162223.v2.0") == date(2024, 12, 31)
    with pytest.raises(SourceError):
        hls_date("HLS.sin-fecha")


def test_the_inner_core_of_a_200_m_plot_is_the_cells_fully_inside_140_m():
    cells = core_cells(ROW, 30, 70)
    assert len(cells) == 4 and len(core_cells(COL, 30, 70)) == 3 and all(abs(i + 0.5 - ROW) * 30 + 15 <= 70 for i in cells)
    assert core_cells(10.0, 30, 10) == []  # un búfer que se come todo no deja celdas
    assert core_cells(10.5, 30, 15) == [10]  # centro de la celda: entra justo una


def test_utm_forward_matches_the_reference_from_proj_and_the_zone_of_an_epsg_is_read():
    assert utm_zone_of_epsg(32616) == (16, True) and utm_zone_of_epsg(32716) == (16, False)
    with pytest.raises(ValueError):
        utm_zone_of_epsg(4326)
    assert utm_forward(-87.0, 0.0, 16) == pytest.approx((500000.0, 0.0), abs=1e-3)  # el meridiano central cae en el falso este


def test_a_clear_hls_scene_gives_the_median_ndvi_of_the_clean_pixels():
    scene, files = hls_scene(fmask=full(0, dtype="u1"), red=full(1000), nir=full(5000))
    o = observe_hls(client_for(files), scene, LON, LAT, "t")
    assert o.ndvi == pytest.approx((0.5 - 0.1) / 0.6) and o.sensor == "HLS-L30" and o.date == date(2025, 3, 8)
    assert o.n_cells == 12 and o.n_valid == 12


def test_cloudy_pixels_are_left_out_of_the_median_but_the_scene_still_counts_with_enough_clear_ones():
    fmask, nir = full(0, dtype="u1"), full(5000)
    r, c = core_cells(ROW, 30, 70), core_cells(COL, 30, 70)
    fmask[r[0], c[0]] = 0b10          # nube
    nir[r[0], c[0]] = 20000           # que, de contarse, movería el resultado
    fmask[r[1], c[1]] = 0b1000        # sombra de nube
    scene, files = hls_scene(fmask=fmask, red=full(1000), nir=nir)
    o = observe_hls(client_for(files), scene, LON, LAT, "t")
    assert o.n_valid == 10 and o.ndvi == pytest.approx(0.4 / 0.6)


def test_each_bad_fmask_bit_discards_the_pixel_but_the_unused_high_bits_do_not():
    for bit in (0b1, 0b10, 0b100, 0b1000, 0b10000, 0b100000):  # cirro, nube, adyacente, sombra, nieve, agua
        fm = full(0, dtype="u1")
        r, c = core_cells(ROW, 30, 70), core_cells(COL, 30, 70)
        fm[r[0], c[0]] = bit
        scene, files = hls_scene(fmask=fm, red=full(1000), nir=full(5000))
        assert observe_hls(client_for(files), scene, LON, LAT, "t").n_valid == 11, bit
    fm = full(0b11000000, dtype="u1")  # aerosol: no descarta el píxel
    scene, files = hls_scene(fmask=fm, red=full(1000), nir=full(5000))
    assert observe_hls(client_for(files), scene, LON, LAT, "t").n_valid == 12


def test_a_scene_with_clouds_over_the_plot_does_not_read_the_reflectance_bands():
    scene, files = hls_scene(fmask=full(0b10, dtype="u1"), red=full(1000), nir=full(5000))
    c = client_for(files)
    o = observe_hls(c, scene, LON, LAT, "t")
    assert math.isnan(o.ndvi) and o.n_valid == 0 and o.n_cells == 12
    assert all("R.tif" not in u and "N.tif" not in u for u, _ in c.once.seen)


def test_less_than_half_of_clear_pixels_makes_the_scene_not_count():
    fm = full(0, dtype="u1")
    r, c = core_cells(ROW, 30, 70), core_cells(COL, 30, 70)
    for i in r[:3]:
        for j in c:
            fm[i, j] = 0b10  # 9 de 12 con nube
    scene, files = hls_scene(fmask=fm, red=full(1000), nir=full(5000))
    o = observe_hls(client_for(files), scene, LON, LAT, "t")
    assert math.isnan(o.ndvi) and o.n_valid == 3


def test_nodata_pixels_in_the_bands_are_not_used():
    red, nir = full(1000), full(5000)
    r, c = core_cells(ROW, 30, 70), core_cells(COL, 30, 70)
    nir[r[0], c[0]] = -9999
    scene, files = hls_scene(fmask=full(0, dtype="u1"), red=red, nir=nir)
    o = observe_hls(client_for(files), scene, LON, LAT, "t")
    assert o.n_valid == 11 and o.ndvi == pytest.approx(0.4 / 0.6)


def test_a_sentinel_based_hls_scene_reads_b8a_not_b05():
    scene, files = hls_scene("HLS.S30.T16QBH.2025070T162223.v2.0", fmask=full(0, dtype="u1"), red=full(1000), nir=full(3000), nir_band="B8A")
    o = observe_hls(client_for(files), scene, LON, LAT, "t")
    assert o.sensor == "HLS-S30" and o.ndvi == pytest.approx(0.2 / 0.4)
    scene["assets"]["B05"] = scene["assets"].pop("B8A")  # con B05 en una escena S30 falta la banda correcta
    with pytest.raises(SourceError, match="faltan archivos"):
        observe_hls(client_for(files), scene, LON, LAT, "t")


def test_a_plot_at_the_edge_of_the_tile_is_refused_not_clipped():
    scene, files = hls_scene(fmask=full(0, shape=(8, 8), dtype="u1"), red=full(1000, (8, 8)), nir=full(5000, (8, 8)))
    with pytest.raises(SourceError, match="borde del mosaico"):
        observe_hls(client_for(files), scene, LON, LAT, "t")


def s2_scene(*, red_raw, nir_raw, scl, nodata="0"):
    files = {
        "https://x/red.tif": tif(full(red_raw, (200, 220), "u2"), 10.0, nodata=nodata),
        "https://x/nir.tif": tif(full(nir_raw, (200, 220), "u2"), 10.0, nodata=nodata),
        "https://x/scl.tif": tif(scl, 20.0, nodata="0"),
    }
    a = {"red": {"href": "https://x/red.tif", "scale": 0.0001, "offset": -0.1, "nodata": 0}, "nir": {"href": "https://x/nir.tif", "scale": 0.0001, "offset": -0.1, "nodata": 0},
         "scl": {"href": "https://x/scl.tif"}}
    return {"id": "S2B_16QBH_20250310_0_L2A", "datetime": datetime(2025, 3, 10, 16, 30), "assets": a}, files


def test_a_sentinel_2_scene_applies_the_offset_and_the_scene_classification():
    scl = full(4, (100, 110), "u1")
    scene, files = s2_scene(red_raw=2000, nir_raw=7000, scl=scl)
    o = observe_s2(client_for(files), scene, LON, LAT)
    r, n = 2000 * 1e-4 - 0.1, 7000 * 1e-4 - 0.1
    assert o.ndvi == pytest.approx((n - r) / (n + r)) and o.sensor == "S2" and o.date == date(2025, 3, 10)
    assert o.n_cells == 13 * 13 and o.n_valid == o.n_cells  # celdas de 10 m con centro a ≤ 65 m: 13 por lado


def test_sentinel_2_cloud_classes_discard_the_scene_without_reading_reflectance():
    scene, files = s2_scene(red_raw=2000, nir_raw=7000, scl=full(9, (100, 110), "u1"))  # nube de probabilidad alta
    c = client_for(files)
    o = observe_s2(c, scene, LON, LAT)
    assert math.isnan(o.ndvi) and o.n_valid == 0
    assert not any(u.endswith("nir.tif") and r != "bytes=0-32767" for u, r in c.once.seen)


def test_a_sentinel_2_scene_without_scale_or_files_is_an_error():
    scene, files = s2_scene(red_raw=2000, nir_raw=7000, scl=full(4, (100, 110), "u1"))
    scene["assets"]["red"]["scale"] = None
    with pytest.raises(SourceError, match="escala"):
        observe_s2(client_for(files), scene, LON, LAT)
    del scene["assets"]["scl"]
    with pytest.raises(SourceError, match="faltan archivos"):
        observe_s2(client_for(files), scene, LON, LAT)


def test_one_scene_that_fails_is_noted_and_the_rest_continue():
    def fn(scene):
        if scene["id"] == "a":
            raise SourceError("sin archivo")
        if scene["id"] == "b":
            raise KeyError("raro")
        return Observation(date(2025, 1, 1), "HLS-L30", scene["id"], 0.5, 12, 12)

    obs, errors = observe_many(fn, [{"id": "a"}, {"id": "b"}, {"id": "c"}], workers=2)
    assert [o.scene for o in obs] == ["c"]
    assert any("a: sin archivo" in e for e in errors) and any("b: inesperado: KeyError" in e for e in errors)


# --- cover.fetch_cover ---------------------------------------------------------------------------------------------

def scene_meta(sid, cloud=10, when=None, epsg=None):
    return {"id": sid, "cloud": cloud, "datetime": when, "epsg": epsg}


def obs(day, ndvi, sensor="HLS-L30", scene="s"):
    return Observation(day, sensor, scene, ndvi, 16, 12 if np.isfinite(ndvi) else 0)


def test_only_the_utm_zone_tile_and_moderate_cloud_scenes_are_read(monkeypatch):
    seen = []

    def fake(client, scene, lon, lat, token, side_m=200):
        seen.append(scene["id"])
        return obs(date(2025, 1, 15), 0.6, scene=scene["id"])

    monkeypatch.setattr(cover_mod, "observe_hls", fake)
    scenes = [scene_meta("HLS.L30.T16QBH.2025015T162223.v2.0"), scene_meta("HLS.L30.T15QZH.2025015T162223.v2.0"),
              scene_meta("HLS.L30.T16QBH.2025016T162223.v2.0", cloud=95), scene_meta("HLS.S30.T16QBH.2025017T162223.v2.0", cloud=None)]
    f = cover_mod.fetch_cover(Client(sleep=lambda s: None), scenes, None, LON, LAT, "2025-01-01", "2025-01-31", token="t", workers=1)
    assert sorted(seen) == ["HLS.L30.T16QBH.2025015T162223.v2.0", "HLS.S30.T16QBH.2025017T162223.v2.0"]
    assert len(f.data) == 2 and f.prov.params["zone"] == 16


def test_with_no_scene_in_the_tile_or_none_readable_the_source_fails_with_a_reason(monkeypatch):
    c = Client(sleep=lambda s: None)
    with pytest.raises(SourceError, match="no hay escenas de HLS del mosaico de la zona 16"):
        cover_mod.fetch_cover(c, [scene_meta("HLS.L30.T15QZH.2025015T162223.v2.0")], None, LON, LAT, "2025-01-01", "2025-01-31", token="t")

    def boom(*a, **k):
        raise SourceError("sin acceso")

    monkeypatch.setattr(cover_mod, "observe_hls", boom)
    with pytest.raises(SourceError, match="ninguna escena de HLS se pudo leer: HLS.L30.T16QBH.2025015T162223.v2.0: sin acceso"):
        cover_mod.fetch_cover(c, [scene_meta("HLS.L30.T16QBH.2025015T162223.v2.0")], None, LON, LAT, "2025-01-01", "2025-01-31", token="t")


def test_sentinel_2_is_tried_only_for_months_without_a_clear_hls_scene_and_stops_at_the_first_that_works(monkeypatch):
    monkeypatch.setattr(cover_mod, "observe_hls", lambda client, scene, lon, lat, token, side_m=200: (
        obs(date(2025, 1, 15), 0.6, scene=scene["id"]) if "2025015" in scene["id"] else obs(date(2025, 2, 10), float("nan"), scene=scene["id"])))
    tried = []

    def fake_s2(client, scene, lon, lat, side_m=200):
        tried.append(scene["id"])
        if scene["id"].endswith("_a"):
            return obs(scene["datetime"].date(), float("nan"), "S2", scene["id"])  # nublada sobre la parcela
        return obs(scene["datetime"].date(), 0.2, "S2", scene["id"])

    monkeypatch.setattr(cover_mod, "observe_s2", fake_s2)
    hls = [scene_meta("HLS.L30.T16QBH.2025015T162223.v2.0"), scene_meta("HLS.L30.T16QBH.2025041T162223.v2.0")]
    s2 = [scene_meta("S2_jan", 5, datetime(2025, 1, 5)), scene_meta("S2_feb_a", 3, datetime(2025, 2, 5)), scene_meta("S2_feb_b", 8, datetime(2025, 2, 15)),
          scene_meta("S2_feb_c", 9, datetime(2025, 2, 25)), scene_meta("S2_feb_nublada", 60, datetime(2025, 2, 26)), scene_meta("S2_feb_otra_zona", 1, datetime(2025, 2, 6), epsg=32615)]
    f = cover_mod.fetch_cover(Client(sleep=lambda s: None), hls, s2, LON, LAT, "2025-01-01", "2025-02-28", token="t", workers=1)
    assert "S2_jan" not in tried                                   # enero ya tenía HLS despejada
    assert "S2_feb_nublada" not in tried and "S2_feb_otra_zona" not in tried
    assert tried == ["S2_feb_a", "S2_feb_b"]              # la más despejada falló; la siguiente sirvió y se paró
    assert sum(o.sensor == "S2" for o in f.data) == 1 and any("1 meses completados con Sentinel-2" in n for n in f.notes)
