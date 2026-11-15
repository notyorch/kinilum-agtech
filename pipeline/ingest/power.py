"""NASA POWER, clima diario en un punto (comunidad AG). Soporte: región (~0.5° × 0.625°). Sin llave.

POWER advierte que pedir muchas veces lo mismo puede terminar en bloqueo: toda petición pasa por la
caché del cliente y se pide un año por vez.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .contract import Fetch, Provenance, Series, SourceError, combined_sha
from .http import Client

URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMETERS = ("PRECTOTCORR", "T2M", "T2M_MAX", "T2M_MIN", "RH2M", "WS2M", "ALLSKY_SFC_SW_DWN")
FILL = -999.0
NATIVE_RES_M = 55_000


def parse_year(body: Any) -> tuple[dict[str, dict[str, float]], dict[str, str]]:
    """Una respuesta de POWER → {variable: {AAAAMMDD: valor}} y unidades. Lanza SourceError si no trae datos."""
    try:
        par = body["properties"]["parameter"]
    except (KeyError, TypeError):
        msg = body.get("messages") or body.get("message") if isinstance(body, dict) else body
        raise SourceError(f"POWER respondió sin datos: {str(msg)[:160]}") from None
    units = {k: v.get("units", "") for k, v in (body.get("parameters") or {}).items()}
    return par, units


def fetch_power(
    client: Client, lon: float, lat: float, start: str, end: str, parameters: tuple[str, ...] = PARAMETERS
) -> Fetch:
    values: dict[str, dict[str, float]] = {p: {} for p in parameters}
    units: dict[str, str] = {}
    shas: list[str] = []
    for year in range(int(start[:4]), int(end[:4]) + 1):  # una petición por año
        s, e = max(start, f"{year}-01-01"), min(end, f"{year}-12-31")
        r = client.get_json(
            URL,
            params={
                "parameters": ",".join(parameters),
                "community": "AG",
                "longitude": lon,
                "latitude": lat,
                "start": s.replace("-", ""),
                "end": e.replace("-", ""),
                "format": "JSON",
            },
        )
        par, u = parse_year(r.body)
        units.update(u)
        shas.append(r.sha256)
        for name in parameters:
            values[name].update(par.get(name, {}))

    days = sorted({d for col in values.values() for d in col})
    if not days:
        raise SourceError("POWER no devolvió ningún día")
    dates = np.array([f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days], dtype="datetime64[D]")
    cols = {
        name: np.array([np.nan if (v := values[name].get(d, np.nan)) == FILL else v for d in days], dtype=float)
        for name in parameters
    }
    prov = Provenance(
        "NASA POWER",
        "daily point (AG)",
        URL,
        {"lon": lon, "lat": lat, "start": start, "end": end, "parameters": list(parameters)},
        response_sha256=combined_sha(shas),
        license="Datos abiertos NASA",
        citation="NASA POWER Project, power.larc.nasa.gov",
    )
    return Fetch(Series(dates, cols, units), prov, units, ["Resolución nativa ~0.5° × 0.625° (región)"])
