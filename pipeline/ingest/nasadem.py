"""NASADEM (NASA JPL / LP DAAC): elevación y pendiente a 30 m. Soporte: parcela. Requiere token de Earthdata.

Un tile `.hgt` de 1° × 1° es una matriz plana de enteros de 16 bits (big-endian), de norte a sur y de oeste a este,
con 3601 muestras por lado. No hace falta ninguna librería: el ZIP se abre con la biblioteca estándar.

La elevación y la pendiente salen de los píxeles que quedan COMPLETOS dentro de la parcela una vez descartado el
borde de 30 m (regla del PRD). La pendiente usa el método de Horn sobre los ocho vecinos de cada píxel.
"""

from __future__ import annotations

import io
import math
import zipfile
from typing import Any

import numpy as np

from .contract import Fetch, Provenance, SourceError, plot_bbox
from .earthdata import PRODUCTS, find_granule
from .http import Client

VOID = -32768
NATIVE_RES_M = 30
MAX_ZIP_BYTES = 64_000_000  # un tile pesa ~7 MB
MAX_HGT_BYTES = 40_000_000  # 3601 × 3601 × 2 = 26 MB; un tope contra un ZIP malicioso
M_PER_DEG_LAT = 110_574
M_PER_DEG_LON_EQ = 111_320


def read_hgt(raw: bytes) -> np.ndarray:
    n = math.isqrt(len(raw) // 2)
    if n < 3 or n * n * 2 != len(raw):
        raise SourceError(f"el .hgt mide {len(raw)} bytes, que no es una matriz cuadrada de enteros de 16 bits")
    return np.frombuffer(raw, dtype=">i2").reshape(n, n)


def hgt_from_zip(data: bytes) -> np.ndarray:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise SourceError("el archivo de NASADEM no es un ZIP válido") from e
    names = [i for i in zf.infolist() if i.filename.lower().endswith(".hgt")]
    if not names:
        raise SourceError("el ZIP de NASADEM no trae un archivo .hgt")
    if names[0].file_size > MAX_HGT_BYTES:
        raise SourceError("el .hgt descomprimido pasa del tope esperado")
    return read_hgt(zf.read(names[0]))


def _pcts(values: np.ndarray) -> dict[str, float]:
    return {"p10": float(np.nanpercentile(values, 10)), "p50": float(np.nanpercentile(values, 50)), "p90": float(np.nanpercentile(values, 90))}


def terrain(tile: np.ndarray, lon: float, lat: float, side_m: float = 200, buffer_m: float = 30) -> dict[str, Any]:
    """Elevación del punto y pendiente de los píxeles limpios de la parcela, de un tile cuya esquina SO es floor(lat), floor(lon)."""
    n = tile.shape[0]
    res = 1.0 / (n - 1)  # grados por muestra
    r0 = (math.floor(lat) + 1 - lat) / res  # posición fraccionaria del punto: fila 0 = borde norte
    c0 = (lon - math.floor(lon)) / res  # columna 0 = borde oeste
    dy = M_PER_DEG_LAT * res
    dx = M_PER_DEG_LON_EQ * math.cos(math.radians(lat)) * res
    half = side_m / 2 - buffer_m  # semilado del núcleo limpio

    rows = [r for r in range(math.floor(r0 - half / dy) - 1, math.ceil(r0 + half / dy) + 2) if abs(r - r0) * dy + dy / 2 <= half]
    cols = [c for c in range(math.floor(c0 - half / dx) - 1, math.ceil(c0 + half / dx) + 2) if abs(c - c0) * dx + dx / 2 <= half]
    if not rows or not cols:
        raise SourceError(f"la parcela de {side_m:g} m no deja ningún píxel completo de {dy:.0f} m tras descartar {buffer_m:g} m")
    pr, pc = round(r0), round(c0)
    if min(rows) < 1 or min(cols) < 1 or max(rows) > n - 2 or max(cols) > n - 2 or not (0 <= pr < n and 0 <= pc < n):
        raise SourceError("la parcela queda en el borde del tile: falta el tile vecino")

    z = tile.astype(float)
    z[tile == VOID] = np.nan
    r_lo, r_hi, c_lo, c_hi = min(rows), max(rows), min(cols), max(cols)
    w = z[r_lo - 1 : r_hi + 2, c_lo - 1 : c_hi + 2]  # el bloque con su anillo de vecinos
    a, b, c = w[:-2, :-2], w[:-2, 1:-1], w[:-2, 2:]
    d, f = w[1:-1, :-2], w[1:-1, 2:]
    g, h, i = w[2:, :-2], w[2:, 1:-1], w[2:, 2:]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * dy)
    slope = 100 * np.hypot(dzdx, dzdy)
    core = z[r_lo : r_hi + 1, c_lo : c_hi + 1]
    voids = int(np.isnan(core).sum())
    if np.isnan(slope).all() or np.isnan(core).all():
        raise SourceError("todos los píxeles limpios de la parcela son vacíos en NASADEM")
    point = z[pr, pc]
    return {
        "elevation_m": {"point": None if np.isnan(point) else float(point), **_pcts(core)},
        "slope_pct": _pcts(slope),
        "clean_cells": int(core.size),
        "void_cells": voids,
        "sample_spacing_m": {"north_south": round(dy, 1), "east_west": round(dx, 1)},
        "tile_samples": int(n),
    }


def tile_name(lon: float, lat: float) -> str:
    return f"NASADEM_HGT_{'n' if lat >= 0 else 's'}{abs(math.floor(lat)):02d}{'e' if lon >= 0 else 'w'}{abs(math.floor(lon)):03d}"


def fetch_nasadem(client: Client, lon: float, lat: float, side_m: float = 200, *, token: str) -> Fetch:
    granule = find_granule(client, PRODUCTS["nasadem"], plot_bbox(lon, lat, side_m))
    expected = tile_name(lon, lat)
    if granule["title"] != expected:
        raise SourceError(f"CMR devolvió {granule['title']} y el punto cae en {expected}: la parcela cruza dos tiles")
    r = client.get_authenticated(granule["url"], token=token, max_bytes=MAX_ZIP_BYTES, timeout=180, binary=True)
    data = terrain(hgt_from_zip(r.body), lon, lat, side_m)
    prov = Provenance(
        "NASADEM (NASA JPL / LP DAAC)",
        "NASADEM_HGT 001",
        r.url,
        {"lon": lon, "lat": lat, "side_m": side_m, "tile": expected},
        response_sha256=r.sha256,
        license="Datos abiertos NASA",
        citation="NASA JPL (2020). NASADEM Merged DEM Global 1 arc second V001. NASA EOSDIS LP DAAC. doi:10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001",
    )
    notes = [f"Tile {expected}; {data['clean_cells']} píxeles limpios de ~{data['sample_spacing_m']['north_south']:.0f} m tras descartar 30 m de borde"]
    if data["void_cells"]:
        notes.append(f"{data['void_cells']} píxeles vacíos entre los limpios")
    return Fetch(data, prov, {"elevation_m": "m", "slope_pct": "%"}, notes)
