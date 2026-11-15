"""SoilGrids (ISRIC), propiedades del suelo a 250 m. Externa a la NASA: papel de complemento. Sin llave.

El servicio puede responder 200 con todos los valores nulos (celda sin dato). Eso es «sin dato», no «ok».
Es lento: pide un tiempo máximo largo. El rango son los cuantiles 5 y 95, no el 10 y el 90.
"""

from __future__ import annotations

from .contract import Fetch, Provenance, SourceError
from .http import Client

URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPERTIES = ("clay", "sand", "silt", "soc", "phh2o", "bdod")
DEPTHS = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm")
NATIVE_RES_M = 250
_KEYS = {"mean": "mean", "Q0.05": "q05", "Q0.95": "q95"}


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
        raise SourceError(f"SoilGrids no tiene valores en este punto: las {len(rows)} capas llegaron nulas (celda sin dato)")
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
