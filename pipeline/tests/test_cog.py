"""El lector de GeoTIFF en la nube contra archivos construidos aquí y contra los valores validados con GDAL."""

import numpy as np
import pytest

from cogfile import build_cog, serve
from ingest import cog as cogmod
from ingest.cog import COG
from ingest.contract import SourceError
from ingest.http import Client

URL = "https://data.lpdaac.earthdatacloud.nasa.gov/x/B04.tif"


def client_for(raw: bytes, url: str = URL):
    c = Client(sleep=lambda s: None)
    c.once = serve({url: raw})
    return c


def sample(shape=(40, 50), dtype="i2", seed=1):
    rng = np.random.default_rng(seed)
    info = np.iinfo(dtype)
    return rng.integers(max(info.min, -9999), min(info.max, 20000), size=shape).astype(dtype)


def test_the_header_is_read_without_touching_any_tile():
    raw = build_cog(sample())
    c = client_for(raw)
    cog = COG.open(c, URL, token="t")
    assert (cog.width, cog.height, cog.tile_w, cog.tile_h, cog.epsg, cog.nodata, cog.predictor) == (50, 40, 16, 16, 32616, -9999.0, 2)
    assert (cog.origin_x, cog.origin_y, cog.pixel_x, cog.pixel_y) == (199980.0, 2300040.0, 30.0, 30.0) and cog.dtype == np.dtype("<i2")
    assert len(c.once.seen) == 1 and c.once.seen[0][1] == "bytes=0-32767"  # un solo rango, el del encabezado


@pytest.mark.parametrize("dtype", ["i2", "u2", "u1"])
@pytest.mark.parametrize("predictor", [1, 2])
def test_every_window_equals_the_source_array_even_across_tiles_and_at_the_padded_edge(dtype, predictor):
    arr = sample(dtype=dtype)
    cog = COG.open(client_for(build_cog(arr, predictor=predictor)), URL)
    for r0, r1, c0, c1 in [(0, 0, 0, 0), (5, 9, 3, 8), (10, 20, 12, 20), (30, 39, 40, 49), (0, 39, 0, 49)]:  # cruza teselas y llega al borde con relleno
        assert np.array_equal(cog.window(r0, r1, c0, c1), arr[r0 : r1 + 1, c0 : c1 + 1]), (r0, r1, c0, c1)


def test_the_predictor_undoes_wraparound_arithmetic_with_big_jumps_and_negative_values():
    arr = np.array([[-9999, 20000, -9999, 32767, -32768, 0, 1, -1]] * 4, dtype="i2")
    cog = COG.open(client_for(build_cog(arr, tile=8)), URL)
    assert np.array_equal(cog.window(0, 3, 0, 7), arr)


def test_a_big_endian_file_is_read_the_same():
    arr = sample()
    assert np.array_equal(COG.open(client_for(build_cog(arr, byteorder=">")), URL).window(0, 39, 0, 49), arr)


def test_only_the_tiles_that_cover_the_window_are_requested():
    c = client_for(build_cog(sample(shape=(64, 64))))
    cog = COG.open(c, URL)
    before = len(c.once.seen)
    cog.window(18, 22, 18, 22)  # cae dentro de una sola tesela de 16 × 16
    assert len(c.once.seen) - before == 1
    cog.window(14, 18, 14, 18)  # cruza las cuatro teselas de la esquina
    assert len(c.once.seen) - before == 1 + 3  # la primera ya se tenía
    cog.window(18, 22, 18, 22)
    assert len(c.once.seen) - before == 4  # y lo ya leído no se vuelve a pedir


def test_the_position_of_the_example_point_matches_what_gdal_and_proj_say():
    """Valores de referencia de rasterio + PROJ sobre una escena real de HLS: fila 1783.5915, columna 1576.6979."""
    cog = COG.open(client_for(build_cog(sample())), URL)
    row, col = cog.locate(-89.42, 20.30)
    assert row == pytest.approx(1783.5915, abs=1e-3) and col == pytest.approx(1576.6979, abs=1e-3)


def test_an_old_hls_scene_with_a_user_defined_projection_is_read_as_utm_16n():
    raw = build_cog(sample(), user_defined_zone=16)
    cog = COG.open(client_for(raw), URL)
    assert cog.epsg == 32616 and cog.locate(-89.42, 20.30) == pytest.approx((1783.5915, 1576.6979), abs=1e-3)


def test_a_user_defined_projection_that_is_not_utm_on_wgs84_is_refused():
    with pytest.raises(SourceError, match="no es una zona UTM"):
        COG.open(client_for(build_cog(sample(), user_defined_zone=70)), URL)  # 16070 no es una zona UTM


@pytest.mark.parametrize("kwargs,expect", [
    ({"compression": 5}, "compresión 5 no soportada"),
    ({"tiled": False}, "no está organizado en teselas"),
    ({"raster_type": 2}, "solo se soportan rásteres de área"),
    ({"samples": 3}, "solo se soportan archivos de una banda"),
    ({"bigtiff": True}, "no es un TIFF clásico"),
])
def test_what_the_reader_does_not_support_is_refused_with_a_reason_instead_of_guessed(kwargs, expect):
    with pytest.raises(SourceError, match=expect):
        COG.open(client_for(build_cog(sample(), **kwargs)), URL)


def test_a_file_that_is_not_a_tiff_is_refused():
    with pytest.raises(SourceError, match="no es un TIFF"):
        COG.open(client_for(b"<html>Earthdata Login</html>" + b"\x00" * 100), URL)


def test_a_window_outside_the_file_is_refused():
    cog = COG.open(client_for(build_cog(sample())), URL)
    for bad in [(-1, 3, 0, 3), (0, 40, 0, 3), (0, 3, 0, 50), (5, 3, 0, 3)]:
        with pytest.raises(SourceError, match="fuera del archivo"):
            cog.window(*bad)


def test_a_corrupt_tile_is_an_error_not_garbage():
    raw = bytearray(build_cog(sample()))
    raw[-20:] = b"\x00" * 20  # estropea la última tesela
    cog = COG.open(client_for(bytes(raw)), URL)
    with pytest.raises(SourceError, match="no se pudo descomprimir"):
        cog.window(30, 39, 40, 49)


def test_a_header_bigger_than_the_first_read_is_read_again_with_more_bytes(monkeypatch):
    raw = build_cog(sample(shape=(200, 200), dtype="i2"), tile=4)  # 2,500 teselas: los arreglos de offsets pasan de 4 KB
    monkeypatch.setattr(cogmod, "HEADER_BYTES", (2_000, 262_144))
    c = client_for(raw)
    cog = COG.open(c, URL)
    assert len(cog.offsets) == 2500 and [r for _, r in c.once.seen] == ["bytes=0-1999", "bytes=0-262143"]


def test_a_server_that_ignores_the_range_is_an_error_not_wrong_bytes():
    c = Client(sleep=lambda s: None)
    c.once = lambda url, headers, timeout: (200, {"Content-Length": "100"}, b"\x00" * 100)
    with pytest.raises(SourceError, match="ignoró el rango"):
        c.get_range(URL, 50, 20)


def test_the_range_cache_and_the_signed_url_never_leave_the_process(tmp_path):
    raw = build_cog(sample())
    signed = "https://d111.cloudfront.net/f.tif?Signature=SECRETA&Expires=1"
    calls = []

    def once(url, headers, timeout):
        calls.append(url)
        if url == URL:
            return 303, {"Location": signed}, b""
        a, b = headers["Range"].removeprefix("bytes=").split("-")
        return 206, {"Content-Range": f"bytes {a}-{min(int(b), len(raw) - 1)}/{len(raw)}"}, raw[int(a) : int(b) + 1]

    c = Client(tmp_path, sleep=lambda s: None)
    c.once = once
    c.get_range(URL, 0, 100, token="tok")
    c.get_range(URL, 200, 50, token="tok")
    assert calls == [URL, signed, signed]  # la segunda lectura reutiliza la URL firmada, sin volver a Earthdata
    assert all("SECRETA" not in p.name and b"SECRETA" not in p.read_bytes() for p in tmp_path.iterdir())
