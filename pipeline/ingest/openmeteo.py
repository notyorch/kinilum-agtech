"""Open-Meteo, archivo histórico (reanálisis ERA5). Externa a la NASA: papel de contraste. Sin llave.

Se muestra siempre como «Open-Meteo (ERA5)», nunca como dato de la NASA. Pide atribución y limita el
uso comercial: revisar la licencia antes de publicar.
"""

from __future__ import annotations

import numpy as np

from .contract import Fetch, Provenance, Series, SourceError
from .http import Client

URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = ("precipitation_sum", "et0_fao_evapotranspiration", "temperature_2m_max", "temperature_2m_min", "shortwave_radiation_sum")
NATIVE_RES_M = 25_000


def fetch_openmeteo(
    client: Client, lon: float, lat: float, start: str, end: str, daily: tuple[str, ...] = DAILY, models: str | None = None
) -> Fetch:
    params = {"latitude": lat, "longitude": lon, "start_date": start, "end_date": end, "daily": ",".join(daily), "timezone": "UTC"}
    if models:
        params["models"] = models
    r = client.get_json(URL, params=params)
    body = r.body
    if not isinstance(body, dict) or "daily" not in body or "time" not in body["daily"]:
        raise SourceError(f"Open-Meteo respondió sin datos: {str(body.get('reason') if isinstance(body, dict) else body)[:160]}")
    d = body["daily"]
    dates = np.array(d["time"], dtype="datetime64[D]")
    cols = {k: np.array([np.nan if x is None else x for x in d[k]], dtype=float) for k in daily if k in d}
    prov = Provenance(
        "Open-Meteo (ERA5)",
        "archive daily",
        URL,
        params,
        response_sha256=r.sha256,
        license="CC BY 4.0 (Open-Meteo)",
        citation="Open-Meteo.com; datos ERA5 de Copernicus/ECMWF",
    )
    units = body.get("daily_units", {})
    return Fetch(Series(dates, cols, units), prov, units, ["Resolución nativa depende del modelo; registrar `models`."])
