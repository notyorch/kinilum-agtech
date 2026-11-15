"""SMAP L4 (NASA NSIDC DAAC): humedad del suelo a 9 km, de la superficie y de la zona de raíz. Soporte: zona. Con token.

Cada granulo (cada 3 horas) pesa ~143 MB: no se descarga. Como con IMERG, se le pide al servidor OPeNDAP solo la celda
del punto, y solo UN granulo por día (el de las 16:30 UTC): la humedad de la zona de raíz cambia despacio de un día a
otro y así un año son ~365 peticiones en vez de ~2,900.

La malla es la EASE-Grid 2.0 global de 9 km, que no es lat/lon. El índice de la celda se ESTIMA con la fórmula de la
proyección y se COMPRUEBA leyendo `cell_lat` y `cell_lon` del propio archivo en una ventana alrededor: se elige la celda
más cercana de verdad y, si queda a más de 7 km del punto, se rechaza. Una fórmula equivocada no puede dar una celda
equivocada en silencio.
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
SHORT_NAME, VERSION = "SPL4SMGP", "008"
NATIVE_RES_M = 9_000
PAGE_SIZE = 2000
FILL_BELOW = -9000.0  # el relleno es -9999
HHMM = "163000"  # el granulo del día que se muestrea
MAX_CELL_KM = 7.0  # media diagonal de una celda de 9 km
WINDOW = 3  # celdas a cada lado de la estimación
_STAMP = re.compile(r"gph_(\d{8})T(\d{6})_")
_OPENDAP = "https://opendap.earthdata.nasa.gov/collections/"

# EASE-Grid 2.0 global de 9 km: Lambert cilíndrica de áreas iguales (EPSG:6933), paralelo estándar 30°.
_A, _F, _PHI1 = 6378137.0, 1 / 298.257223563, math.radians(30)
_E2 = _F * (2 - _F)
_E = math.sqrt(_E2)
_K0 = math.cos(_PHI1) / math.sqrt(1 - _E2 * math.sin(_PHI1) ** 2)
_CELL, _ULX, _ULY = 9008.055210146, -17367530.445161499, 7314540.830638599


def ease_estimate(lon: float, lat: float) -> tuple[float, float]:
    """(fila, columna) fraccionarias de la celda del punto en la malla de 3856 × 1624. Es una ESTIMACIÓN: se comprueba."""
    s = math.sin(math.radians(lat))
    q = (1 - _E2) * (s / (1 - _E2 * s * s) - (1 / (2 * _E)) * math.log((1 - _E * s) / (1 + _E * s)))
    x, y = _A * _K0 * math.radians(lon), _A * q / (2 * _K0)
    return (_ULY - y) / _CELL - 0.5, (x - _ULX) / _CELL - 0.5


def ce_url(base: str, ce: str) -> str:
    return f"{base}.dap.csv?dap4.ce=" + quote(ce, safe="/=&?.,")  # corchetes, «:» y «;» codificados, como lo probado contra el servidor


def _error(text: str) -> None:
    if text.lstrip().startswith("Dataset: ERROR"):
        msg = re.search(r'message, "([^"]*)', text)
        raise SourceError(f"OPeNDAP respondió con un error: {(msg.group(1) if msg else 'sin mensaje')[:160]}")


def parse_window(text: str, var: str) -> np.ndarray:
    """El CSV de una ventana 2D → matriz (una fila por renglón de la ventana). El relleno es nan."""
    _error(text)
    rows = [ln for ln in text.splitlines() if ln.startswith(f"/{var}[")]
    if not rows:
        raise SourceError(f"OPeNDAP no devolvió {var}")
    try:
        grid = np.array([[float(v) for v in ln.split(",")[1:] if v.strip()] for ln in rows], dtype=float)
    except ValueError:
        raise SourceError(f"OPeNDAP devolvió un valor que no es número en {var}") from None
    if grid.ndim != 2 or grid.size == 0:
        raise SourceError(f"OPeNDAP devolvió una ventana irregular de {var}")
    grid[grid < FILL_BELOW] = np.nan
    return grid


def _km(lon1: float, lat1: float, lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    p1, p2 = math.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def locate_cell(client: Client, token: str, base: str, lon: float, lat: float) -> dict[str, Any]:
    """La celda más cercana al punto, comprobada contra `cell_lat` y `cell_lon` del archivo."""
    r0, c0 = (round(v) for v in ease_estimate(lon, lat))
    r_lo, c_lo = r0 - WINDOW, c0 - WINDOW
    window = f"[{r_lo}:{r0 + WINDOW}][{c_lo}:{c0 + WINDOW}]"
    got = {}
    for var in ("cell_lat", "cell_lon"):
        got[var] = parse_window(client.get_authenticated(ce_url(base, f"/{var}{window}"), token=token, max_bytes=100_000, timeout=90).body, var)
    dist = _km(lon, lat, got["cell_lon"], got["cell_lat"])
    i, j = np.unravel_index(int(np.argmin(dist)), dist.shape)
    if dist[i, j] > MAX_CELL_KM:
        raise SourceError(f"la celda de SMAP más cercana está a {dist[i, j]:.1f} km del punto: la estimación de la malla falló")
    return {"row": r_lo + int(i), "col": c_lo + int(j), "lat_center": round(float(got["cell_lat"][i, j]), 4),
            "lon_center": round(float(got["cell_lon"][i, j]), 4), "distance_km": round(float(dist[i, j]), 1), "estimate": [round(r0, 0), round(c0, 0)]}


def list_granules(client: Client, start: str, end: str, hhmm: str = HHMM) -> dict[str, str]:
    """{AAAA-MM-DD: enlace OPeNDAP} del granulo de las `hhmm` de cada día, desde CMR (abierto)."""
    out: dict[str, str] = {}
    for page in range(1, 40):
        params = {"short_name": SHORT_NAME, "version": VERSION, "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z", "page_size": PAGE_SIZE, "page_num": page}
        entries = client.get_json(CMR_GRANULES, params=params).body.get("feed", {}).get("entry", [])
        for e in sorted(entries, key=lambda x: x.get("title", "")):  # si hay dos reprocesos del mismo instante, gana el último
            m = _STAMP.search(e.get("title", ""))
            link = next((lnk["href"] for lnk in e.get("links", []) if lnk.get("rel", "").endswith("service#") and lnk["href"].startswith(_OPENDAP)), None)
            if m and link and m.group(2) == hhmm:
                d = m.group(1)
                out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = link
        if len(entries) < PAGE_SIZE:
            break
    return out


def fetch_smap(client: Client, lon: float, lat: float, start: str, end: str, *, token: str, workers: int = 4) -> Fetch:
    granules = {d: u for d, u in list_granules(client, start, end).items() if start <= d <= end}
    if not granules:
        raise SourceError("CMR no tiene granulos de SMAP L4 en ese periodo")
    days = sorted(granules)
    cell = locate_cell(client, token, granules[days[0]], lon, lat)
    r, c = cell["row"], cell["col"]
    ce = f"/Geophysical_Data/sm_rootzone[{r}:{r + 1}][{c}:{c + 1}];/Geophysical_Data/sm_surface[{r}:{r + 1}][{c}:{c + 1}]"

    def one(day: str) -> tuple[str, tuple[float, float] | None, str, str | None]:
        try:
            res = client.get_authenticated(ce_url(granules[day], ce), token=token, max_bytes=100_000, timeout=90)
            root = parse_window(res.body, "Geophysical_Data/sm_rootzone")[0, 0]  # la ventana es de 2 × 2 (una celda sola devuelve vacío)
            surf = parse_window(res.body, "Geophysical_Data/sm_surface")[0, 0]
            return day, (float(root), float(surf)), res.sha256, None
        except SourceError as e:
            return day, None, "", str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, days))

    dates = np.arange(np.datetime64(start), np.datetime64(end) + np.timedelta64(1, "D"), dtype="datetime64[D]")
    index = {str(d): k for k, d in enumerate(dates)}
    root, surf = np.full(len(dates), np.nan), np.full(len(dates), np.nan)
    errors, shas = [], []
    for day, vals, sha, err in results:
        if err or vals is None:
            errors.append(err or "sin valores")
            continue
        shas.append(sha)
        root[index[day]], surf[index[day]] = vals
    if len(errors) == len(results):
        raise SourceError(f"ningún día de SMAP respondió: {errors[0]}")

    prov = Provenance(
        "SMAP L4 (NASA NSIDC DAAC)", f"{SHORT_NAME} v{VERSION}", "https://opendap.earthdata.nasa.gov (OPeNDAP, celda del punto)",
        {"lon": lon, "lat": lat, "start": start, "end": end, "hhmm_utc": hhmm_label(HHMM), "cell": {k: v for k, v in cell.items() if k != "estimate"}},
        response_sha256=combined_sha(shas), license="Datos abiertos NASA",
        citation="SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture Geophysical Data (SPL4SMGP) V008, NASA NSIDC DAAC",
    )
    notes = [f"9 km (zona); celda centrada en {cell['lon_center']}, {cell['lat_center']} ({cell['distance_km']} km del punto); un granulo por día, el de las {hhmm_label(HHMM)} UTC"]
    if len(dates) - len(granules):
        notes.append(f"{len(dates) - len(granules)} días sin granulo de esa hora")
    if errors:
        notes.append(f"{len(errors)} días sin respuesta ({errors[0][:80]})")
    series = Series(dates, {"sm_rootzone": root, "sm_surface": surf}, {"sm_rootzone": "m3/m3", "sm_surface": "m3/m3"})
    return Fetch(series, prov, series.units, notes)


def hhmm_label(hhmm: str) -> str:
    return f"{hhmm[:2]}:{hhmm[2:4]}"
