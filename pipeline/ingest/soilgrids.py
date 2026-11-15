"""SoilGrids (ISRIC), propiedades del suelo a 250 m. Externa a la NASA: papel de complemento. Sin llave.

El servicio puede responder 200 con todos los valores nulos (celda sin dato). Eso es «sin dato», no «ok».
Es lento: pide un tiempo máximo largo. El rango son los cuantiles 5 y 95, no el 10 y el 90.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Iterator

from .contract import Fetch, Provenance, SourceError
from .http import Client

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ("clay", "sand", "silt", "soc", "phh2o", "bdod")
DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm")
NATIVE_RES_M = 250
_KEYS = {"mean": "mean", "Q0.05": "q05", "Q0.95": "q95"}

# El respaldo busca la celda válida más cercana en anillos de 8 direcciones. SoilGrids limita las consultas (unas 5 por
# minuto): entre una y otra se espera `PAUSE_S`.
RADII_M = (250, 500, 1000)
PAUSE_S = 12.0
_BEARINGS = (("norte", 0), ("noreste", 45), ("este", 90), ("sureste", 135), ("sur", 180), ("suroeste", 225), ("oeste", 270), ("noroeste", 315))


class SoilNoData(SourceError):
    """El servicio respondió 200, pero todas las capas llegaron nulas: la celda no tiene valores."""


def fetch_soilgrids(client: Client, lon: float, lat: float, properties: tuple[str, ...] = PROPERTIES, depths: tuple[str, ...] = DEPTHS) -> Fetch:
    params = {"lon": lon, "lat": lat, "property": list(properties), "depth": list(depths), "value": ["mean", "Q0.05", "Q0.95"]}
    r = client.get_json(URL, params=params, timeout=150)
    try:
        layers = r.body["properties"]["layers"]
    except (KeyError, TypeError):
        raise SourceError("SoilGrids respondió sin capas") from None

    rows, notes = [], []
    for layer in layers:
        um = layer.get("unit_measure", {})
        factor = um.get("d_factor")
        if not factor:
            notes.append(f"{layer['name']}: sin d_factor, valores sin convertir")
            factor = 1
        for d in layer["depths"]:
            row = {"property": layer["name"], "depth": d["label"], "units": um.get("target_units")}
            for src, dst in _KEYS.items():
                x = d["values"].get(src)
                row[dst] = None if x is None else x / factor
            rows.append(row)

    nulls = sum(1 for row in rows if row["mean"] is None)
    if not rows or nulls == len(rows):
        raise SoilNoData(f"SoilGrids no tiene valores en este punto: las {len(rows)} capas llegaron nulas (celda sin dato)")
    if nulls:
        notes.append(f"{nulls} de {len(rows)} capas sin valor")
    prov = Provenance(
        "SoilGrids (ISRIC)",
        "properties/query v2.0",
        URL,
        params,
        response_sha256=r.sha256,
        license="CC BY 4.0 (ISRIC)",
        citation="Poggio et al. 2021, SoilGrids 2.0, SOIL 7",
    )
    return Fetch(rows, prov, notes=[*notes, "Rango = cuantiles 5 y 95, no 10 y 90."])


def ring_points(lon: float, lat: float, radii: tuple[int, ...] = RADII_M) -> Iterator[tuple[int, str, float, float]]:
    """(radio en m, dirección, lon, lat) de los 8 puntos de cada anillo, del más cercano al más lejano."""
    for r in radii:
        for name, deg in _BEARINGS:
            theta = math.radians(deg)
            dlat = r * math.cos(theta) / 110_574
            dlon = r * math.sin(theta) / (111_320 * math.cos(math.radians(lat)))
            yield r, name, round(lon + dlon, 6), round(lat + dlat, 6)


def fetch_soilgrids_nearest(
    client: Client, lon: float, lat: float, properties: tuple[str, ...] = PROPERTIES, depths: tuple[str, ...] = DEPTHS,
    *, radii: tuple[int, ...] = RADII_M, pause: float = PAUSE_S, sleep: Callable[[float], None] = time.sleep,
) -> Fetch:
    """SoilGrids del punto; si su celda no tiene valores, el de la celda válida MÁS CERCANA, dicho con claridad.

    Un vecino no es el punto: el resultado lleva la distancia y la dirección en `notes` y en `prov.params["fallback"]`, y
    el contrato lo marca `interpolated`. Primero se sondea cada candidato con una sola capa (clay, 0-5 cm) y solo el
    primero válido se pide completo. Si ninguno tiene valores, es «sin dato».
    """
    try:
        return fetch_soilgrids(client, lon, lat, properties, depths)
    except SoilNoData:
        pass
    for radius, direction, lo, la in ring_points(lon, lat, radii):
        sleep(pause)
        try:
            fetch_soilgrids(client, lo, la, ("clay",), ("0-5cm",))
        except SoilNoData:
            continue
        sleep(pause)
        found = fetch_soilgrids(client, lo, la, properties, depths)
        fallback: dict[str, Any] = {"distance_m": radius, "direction": direction, "lon": lo, "lat": la}
        found.prov.params["fallback"] = fallback
        found.notes.insert(0, f"El punto no tiene valores: se usó la celda válida más cercana, a {radius} m al {direction}")
        return found
    raise SourceError(f"SoilGrids no tiene valores en el punto ni a {max(radii)} m a la redonda")
