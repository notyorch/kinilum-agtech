"""Plantas verdes: el NDVI de la parcela, escena por escena, con la máscara de nubes de cada escena.

Para cada escena se leen, por rangos, solo los píxeles que quedan COMPLETOS dentro de la parcela tras descartar el borde
de 30 m (regla del PRD), se descartan los que la máscara marca como nube, sombra, cirro, nieve o agua, y el NDVI de la
escena es la mediana de los que quedan. Si despejados quedan menos de la mitad, la escena no cuenta.

  HLS         rojo B04 · infrarrojo B05 (Landsat) o B8A (Sentinel-2) · máscara Fmask (por bits), con token de Earthdata.
  Sentinel-2  rojo · infrarrojo · clasificación de escena SCL (a 20 m; la reflectancia a 10 m), sin token. Es el RESPALDO.

NDVI = (IR − rojo) / (IR + rojo). Detecta «plantas verdes», no «suelo desnudo»: no se calcula BSI porque eso afirmaría
suelo desnudo, y el PRD pide hablar de plantas verdes y de rastrojo aparte.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np

from .cog import COG
from .contract import SourceError
from .geo import core_cells
from .http import Client

HLS_SCALE, HLS_NODATA = 0.0001, -9999
FMASK_BAD = 0b00111111  # cirro, nube, adyacente a nube o sombra, sombra, nieve o hielo, agua
SCL_VALID = (4, 5)  # vegetación y no vegetado; fuera: sombras, nubes, cirro, nieve, agua, sin clasificar
MIN_VALID_FRACTION = 0.5  # de los píxeles limpios de la parcela, cuántos deben estar despejados (propuesta)
_HLS_DATE = re.compile(r"\.(\d{4})(\d{3})T\d{6}\.")


@dataclass(frozen=True)
class Observation:
    date: date
    sensor: str  # HLS-L30, HLS-S30 o S2
    scene: str
    ndvi: float  # nan si la escena no cuenta
    n_cells: int
    n_valid: int


def hls_date(scene_id: str) -> date:
    """La fecha de una escena HLS a partir de su identificador: HLS.L30.T16QBH.2025067T162223.v2.0 → día 67 de 2025."""
    m = _HLS_DATE.search(scene_id)
    if not m:
        raise SourceError(f"el identificador {scene_id} no trae fecha")
    return date.fromordinal(date(int(m.group(1)), 1, 1).toordinal() + int(m.group(2)) - 1)


def _ndvi(red: np.ndarray, nir: np.ndarray, valid: np.ndarray, *, scale: float, offset: float, nodata: float | None) -> tuple[float, int]:
    ok = valid.copy()
    if nodata is not None:
        ok &= (red != nodata) & (nir != nodata)
    r, n = red.astype(float) * scale + offset, nir.astype(float) * scale + offset
    denom = n + r
    ok &= denom > 0
    if not ok.any():
        return float("nan"), 0
    ndvi = np.where(ok, (n - r) / np.where(ok, denom, 1), np.nan)
    return float(np.nanmedian(ndvi)), int(ok.sum())


def _core(red: COG, lon: float, lat: float, side_m: float, buffer_m: float) -> tuple[list[int], list[int]]:
    row, col = red.locate(lon, lat)
    half = side_m / 2 - buffer_m
    rows, cols = core_cells(row, red.pixel_y, half), core_cells(col, red.pixel_x, half)
    if not rows or not cols:
        raise SourceError("la parcela no deja ningún píxel completo tras descartar el borde")
    if rows[0] < 0 or cols[0] < 0 or rows[-1] >= red.height or cols[-1] >= red.width:
        raise SourceError("la parcela queda en el borde del mosaico")
    return rows, cols


def observe_hls(client: Client, scene: dict[str, Any], lon: float, lat: float, token: str, side_m: float = 200, buffer_m: float = 30) -> Observation:
    """El NDVI de la parcela en una escena HLS."""
    a = scene["assets"]
    sensor = "HLS-S30" if ".S30." in scene["id"] else "HLS-L30"
    nir_band = "B8A" if sensor == "HLS-S30" else "B05"
    if not all(k in a for k in ("B04", nir_band, "Fmask")):
        raise SourceError(f"a la escena {scene['id']} le faltan archivos (B04, {nir_band} o Fmask)")
    mask = COG.open(client, a["Fmask"]["href"], token)
    rows, cols = _core(mask, lon, lat, side_m, buffer_m)
    r0, r1, c0, c1 = rows[0], rows[-1], cols[0], cols[-1]
    n_cells = len(rows) * len(cols)
    valid = (mask.window(r0, r1, c0, c1) & FMASK_BAD) == 0
    if valid.sum() < MIN_VALID_FRACTION * n_cells:  # nubes sobre la parcela: no se leen las bandas
        return Observation(hls_date(scene["id"]), sensor, scene["id"], float("nan"), n_cells, int(valid.sum()))
    red, nir = COG.open(client, a["B04"]["href"], token), COG.open(client, a[nir_band]["href"], token)
    if (red.origin_x, red.origin_y, red.pixel_x) != (mask.origin_x, mask.origin_y, mask.pixel_x):
        raise SourceError("las bandas de la escena no comparten malla")
    ndvi, n_valid = _ndvi(red.window(r0, r1, c0, c1), nir.window(r0, r1, c0, c1), valid, scale=HLS_SCALE, offset=0.0, nodata=HLS_NODATA)
    if n_valid < MIN_VALID_FRACTION * n_cells:
        ndvi = float("nan")
    return Observation(hls_date(scene["id"]), sensor, scene["id"], ndvi, n_cells, n_valid)


def observe_s2(client: Client, scene: dict[str, Any], lon: float, lat: float, side_m: float = 200, buffer_m: float = 30) -> Observation:
    """El NDVI de la parcela en una escena Sentinel-2 L2A de Earth Search (archivos públicos, sin token)."""
    a = scene["assets"]
    if not all(k in a for k in ("red", "nir", "scl")):
        raise SourceError(f"a la escena {scene['id']} le faltan archivos (red, nir o scl)")
    red, nir, scl = (COG.open(client, a[k]["href"]) for k in ("red", "nir", "scl"))
    if (red.origin_x, red.origin_y, red.pixel_x) != (nir.origin_x, nir.origin_y, nir.pixel_x) or red.epsg != scl.epsg:
        raise SourceError("las bandas de la escena no comparten malla")
    ratio = round(scl.pixel_x / red.pixel_x)
    if abs(scl.origin_x - red.origin_x) > 1e-6 or abs(scl.origin_y - red.origin_y) > 1e-6 or ratio < 1:
        raise SourceError("la clasificación de escena no está alineada con la reflectancia")
    rows, cols = _core(red, lon, lat, side_m, buffer_m)
    r0, r1, c0, c1 = rows[0], rows[-1], cols[0], cols[-1]
    n_cells = len(rows) * len(cols)
    block = scl.window(r0 // ratio, r1 // ratio, c0 // ratio, c1 // ratio)  # cada píxel de 20 m cubre 2 × 2 de 10 m
    scl_at = block[np.ix_([r // ratio - r0 // ratio for r in rows], [c // ratio - c0 // ratio for c in cols])]
    valid = np.isin(scl_at, SCL_VALID)
    day = scene["datetime"].date()
    if valid.sum() < MIN_VALID_FRACTION * n_cells:
        return Observation(day, "S2", scene["id"], float("nan"), n_cells, int(valid.sum()))
    sa, sb = a["red"], a["nir"]
    if sa.get("scale") is None or sb.get("scale") is None:
        raise SourceError("la escena no declara la escala de su reflectancia")
    # La escala y el desplazamiento vienen del STAC (el desplazamiento de -0.1 depende de la línea base de procesamiento).
    ndvi_r = red.window(r0, r1, c0, c1)
    ndvi_n = nir.window(r0, r1, c0, c1)
    r_f = ndvi_r.astype(float) * sa["scale"] + (sa.get("offset") or 0.0)
    n_f = ndvi_n.astype(float) * sb["scale"] + (sb.get("offset") or 0.0)
    ok = valid & (ndvi_r != (sa.get("nodata") if sa.get("nodata") is not None else -1)) & (ndvi_n != (sb.get("nodata") if sb.get("nodata") is not None else -1)) & ((n_f + r_f) > 0)
    if ok.sum() < MIN_VALID_FRACTION * n_cells:
        return Observation(day, "S2", scene["id"], float("nan"), n_cells, int(ok.sum()))
    return Observation(day, "S2", scene["id"], float(np.nanmedian(np.where(ok, (n_f - r_f) / np.where(ok, n_f + r_f, 1), np.nan))), n_cells, int(ok.sum()))


def observe_many(fn, scenes: list[dict[str, Any]], workers: int = 4) -> tuple[list[Observation], list[str]]:
    """Corre `fn(scene)` para cada escena; una escena que falla se anota y no detiene a las demás."""
    def one(scene: dict[str, Any]) -> tuple[Observation | None, str | None]:
        try:
            return fn(scene), None
        except SourceError as e:
            return None, f"{scene['id']}: {e}"
        except Exception as e:  # una escena rara no debe detener cientos de escenas: se anota y se sigue
            return None, f"{scene['id']}: inesperado: {type(e).__name__}: {str(e)[:100]}"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, scenes))
    return [o for o, _ in results if o is not None], [e for _, e in results if e is not None]
