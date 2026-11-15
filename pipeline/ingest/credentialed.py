"""Fuentes que necesitan credencial: esqueletos honestos.

Ninguna lee valores todavía. Sin credencial dicen «falta <VARIABLE>»; con ella dicen que el conector aún no
está integrado. Así ningún estado «ok» ni ningún dato sale de código que nadie ha probado. El ACCESO con token ya
se comprueba aparte, con `python -m ingest.access`. Los secretos se leen de variables de entorno o del `.env`
(que git ignora) y nunca se imprimen ni se guardan.

IMERG, NASADEM y SMAP ya tienen conector (`imerg.py`, `nasadem.py`, `smap.py`). Cómo se completará cada una de las demás:
  - MODIS:     MOD13Q1 (NDVI 250 m, 16 días) del píxel de la parcela y su campo de confiabilidad.
  - SMAP L4, ECOSTRESS, GRACE: recortables; solo si queda tiempo.
  - ERA5-Land: cdsapi; las peticiones hacen fila y las muy grandes se rechazan por costo: pedir solo el punto.
"""

from __future__ import annotations

from .contract import Fetch, SourcePending
from .env import secret


def _pending(env_name: str, todo: str) -> SourcePending:
    if not secret(env_name):
        return SourcePending(f"falta {env_name}")
    return SourcePending(f"conector por integrar: {todo}")


def fetch_modis(*_: object, **__: object) -> Fetch:
    raise _pending("EARTHDATA_TOKEN", "MOD13Q1, serie de NDVI del píxel de la parcela")


def fetch_ecostress(*_: object, **__: object) -> Fetch:
    raise _pending("EARTHDATA_TOKEN", "ECOSTRESS, pasadas irregulares a 70 m")


def fetch_grace(*_: object, **__: object) -> Fetch:
    raise _pending("EARTHDATA_TOKEN", "GRACE/GRACE-FO, mascones de ~300 km")


def fetch_era5land(*_: object, **__: object) -> Fetch:
    raise _pending("CDS_API_KEY", "cdsapi, serie de tiempo del punto")
