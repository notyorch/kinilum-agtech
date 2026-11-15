"""GPM IMERG Final diario (NASA GES DISC), 0.1° (~11 km). Soporte: zona. Requiere token de Earthdata.

El archivo diario global pesa ~28 MB y diez años serían más de 100 GB. Se le pide al servidor OPeNDAP SOLO la celda
del punto de cada día (y la vecina en latitud, que sale gratis). Cuidados con ese servicio (Hyrax):
  - los corchetes de la selección van codificados (con corchetes crudos responde 400),
  - las variables se separan con «;» (DAP4),
  - una selección de UNA sola celda devuelve el CSV vacío: por eso se piden dos.

La corrida Final tarda hasta ~4 meses en publicarse: los días recientes no existen y quedan sin dato.
"""

from __future__ import annotations

import math
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote

import numpy as np

from .contract import Fetch, Provenance, Series, SourceError, combined_sha
from .http import Client

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
SHORT_NAME, VERSION = "GPM_3IMERGDF", "07"
GRID = 0.1
LON0, LAT0 = -179.95, -89.95  # centro de la celda 0
N_LON, N_LAT = 3600, 1800
NATIVE_RES_M = 11_000
PAGE_SIZE = 2000  # tope de CMR por página
FILL_BELOW = -9000.0  # el relleno es -9999.9
EDGE_WARN_DEG = 0.02  # a menos de ~2 km del borde de la celda, la celda vecina podría dar otro resultado
_DATE = re.compile(r"3IMERG\.(\d{8})-S")
_OPENDAP = "https://opendap.earthdata.nasa.gov/collections/"


def cell_index(lon: float, lat: float) -> dict[str, Any]:
    """La celda que CONTIENE el punto (borde inferior incluido) y la pareja de celdas en latitud que se pide.

    `pair` son dos índices de latitud consecutivos; `pos` dice cuál de los dos es la celda del punto. La otra es la
    vecina del lado del borde más cercano. `margin_deg` es la distancia del punto al borde de su celda.
    """
    x, y = round((lon + 180) / GRID, 6), round((lat + 90) / GRID, 6)
    i, j = math.floor(x), math.floor(y)
    if not (0 <= i < N_LON and 1 <= j < N_LAT - 1):
        raise SourceError(f"el punto ({lon}, {lat}) cae fuera de la malla de IMERG")
    fx, fy = x - i, y - j
    south = fy < 0.5
    return {
        "lon_index": i, "lat_index": j, "pair": (j - 1, j) if south else (j, j + 1), "pos": 1 if south else 0,
        "lon_center": round(LON0 + GRID * i, 2), "lat_center": round(LAT0 + GRID * j, 2),
        "margin_deg": round(min(fx, 1 - fx, fy, 1 - fy) * GRID, 4),
    }


def dap_url(base: str, i: int, j_lo: int, j_hi: int) -> str:
    ce = f"/precipitation[0:0][{i}:{i}][{j_lo}:{j_hi}]"
    return f"{base}.dap.csv?dap4.ce=" + quote(ce, safe="/=&?.,")


def parse_point_csv(text: str, n: int = 2) -> list[float | None]:
    """El CSV de OPeNDAP → los `n` valores de precipitación (mm/día); el relleno es None."""
    if text.lstrip().startswith("Dataset: ERROR"):
        msg = re.search(r'message, "([^"]*)', text)
        raise SourceError(f"OPeNDAP respondió con un error: {(msg.group(1) if msg else 'sin mensaje')[:160]}")
    line = next((ln for ln in text.splitlines() if ln.startswith("/precipitation")), None)
    if line is None or "," not in line:
        raise SourceError("OPeNDAP no devolvió la variable precipitation")
    cells = [c.strip() for c in line.split(",")[1:] if c.strip()]
    if len(cells) != n:
        raise SourceError(f"OPeNDAP devolvió {len(cells)} valores y se esperaban {n}")
    try:
        values = [float(c) for c in cells]
    except ValueError:
        raise SourceError("OPeNDAP devolvió un valor que no es número") from None
    return [None if v < FILL_BELOW else v for v in values]


def list_granules(client: Client, start: str, end: str) -> dict[str, str]:
    """{AAAA-MM-DD: enlace OPeNDAP del granulo} de la corrida Final, desde CMR (abierto)."""
    out: dict[str, str] = {}
    for page in range(1, 20):
        params = {"short_name": SHORT_NAME, "version": VERSION, "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z", "page_size": PAGE_SIZE, "page_num": page}
        entries = client.get_json(CMR_GRANULES, params=params).body.get("feed", {}).get("entry", [])
        for e in entries:
            m = _DATE.search(e.get("title", ""))
            link = next((lnk["href"] for lnk in e.get("links", []) if lnk.get("rel", "").endswith("service#") and lnk["href"].startswith(_OPENDAP)), None)
            if m and link:
                d = m.group(1)
                out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = link
        if len(entries) < PAGE_SIZE:
            break
    return out


def fetch_imerg(client: Client, lon: float, lat: float, start: str, end: str, *, token: str, workers: int = 4) -> Fetch:
    cell = cell_index(lon, lat)
    # Solo los días del periodo pedido: un granulo de más no se pide ni descuadra la serie.
    granules = {d: u for d, u in list_granules(client, start, end).items() if start <= d <= end}
    if not granules:
        raise SourceError("CMR no tiene granulos de IMERG Final en ese periodo")
    lo, hi = cell["pair"]

    def one(day: str) -> tuple[str, list[float | None] | None, str, str | None]:
        try:
            r = client.get_authenticated(dap_url(granules[day], cell["lon_index"], lo, hi), token=token, max_bytes=100_000, timeout=60)
            return day, parse_point_csv(r.body), r.sha256, None
        except SourceError as e:
            return day, None, "", str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, sorted(granules)))

    dates = np.arange(np.datetime64(start), np.datetime64(end) + np.timedelta64(1, "D"), dtype="datetime64[D]")
    index = {str(d): k for k, d in enumerate(dates)}
    point, neighbor = np.full(len(dates), np.nan), np.full(len(dates), np.nan)
    errors, shas = [], []
    for day, vals, sha, err in results:
        if err or vals is None:
            errors.append(err or "sin valores")
            continue
        shas.append(sha)
        k = index[day]
        pv, nv = vals[cell["pos"]], vals[1 - cell["pos"]]
        point[k] = np.nan if pv is None else pv
        neighbor[k] = np.nan if nv is None else nv
    if len(errors) == len(results):
        raise SourceError(f"ningún día de IMERG respondió: {errors[0]}")

    prov = Provenance(
        "GPM IMERG Final (NASA GES DISC)", f"{SHORT_NAME} v{VERSION}", "https://opendap.earthdata.nasa.gov (OPeNDAP, celda del punto)",
        {"lon": lon, "lat": lat, "start": start, "end": end, "cell": {k: v for k, v in cell.items() if k not in ("pair", "pos")}},
        response_sha256=combined_sha(shas), license="Datos abiertos NASA",
        citation="Huffman et al., GPM IMERG Final Daily V07, NASA GES DISC",
    )
    notes = [f"0.1° (~11 km, zona); celda centrada en {cell['lon_center']}, {cell['lat_center']}"]
    missing = len(dates) - len(granules)
    if missing:
        notes.append(f"{missing} días sin granulo (la corrida Final llega hasta {max(granules)})")
    if errors:
        notes.append(f"{len(errors)} días sin respuesta ({errors[0][:80]})")
    if cell["margin_deg"] < EDGE_WARN_DEG:
        notes.append(f"el punto está a {cell['margin_deg']}° del borde de la celda: la vecina en latitud puede dar otro resultado")
    series = Series(dates, {"precip_mm_day": point, "neighbor_mm_day": neighbor}, {"precip_mm_day": "mm/day", "neighbor_mm_day": "mm/day"})
    return Fetch(series, prov, series.units, notes)
