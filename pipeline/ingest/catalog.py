"""Catálogo de fuentes: es un dato. Añadir una fuente es añadir una fila aquí y su conector en `load.py`.

`role`:  core (núcleo) · fifth (quinta fuente del mínimo) · trimmable (recortable) · contrast · complement · backup ·
         derived (lee los píxeles de una fuente que ya está en el catálogo, como `hls_ndvi` de `hls_stac`).
`access`: open (sin llave) · search-open (buscar abierto, descargar con token) · earthdata (token Earthdata) ·
          cds (llave de Copernicus CDS).
`support` sale de la resolución nativa (`contract.support_level`), no se escribe a mano.
"""

from __future__ import annotations

from typing import Any

from .contract import support_level

_NASA = "Datos abiertos NASA"

SOURCES: list[dict[str, Any]] = [
    {"id": "power", "name": "NASA POWER", "origin": "nasa", "role": "core", "access": "open", "native_res_m": 55_000, "cadence": "daily", "priority": "P0", "token_env": None, "license": _NASA, "citation": "NASA POWER Project, power.larc.nasa.gov"},
    {"id": "imerg", "name": "GPM IMERG Final", "origin": "nasa", "role": "core", "access": "earthdata", "native_res_m": 11_000, "cadence": "daily (latencia ~4 meses)", "priority": "P0", "token_env": "EARTHDATA_TOKEN", "license": _NASA, "citation": "Huffman et al., GPM IMERG Final Daily V07, GES DISC"},
    {"id": "hls_stac", "name": "HLS (Landsat + Sentinel-2)", "origin": "nasa", "role": "core", "access": "search-open", "native_res_m": 30, "cadence": "2 a 3 días", "priority": "P0", "token_env": None, "license": _NASA, "citation": "NASA LP DAAC, HLS v2.0"},
    {"id": "nasadem", "name": "NASADEM / SRTM", "origin": "nasa", "role": "core", "access": "earthdata", "native_res_m": 30, "cadence": "estático", "priority": "P0", "token_env": "EARTHDATA_TOKEN", "license": _NASA, "citation": "NASA JPL, NASADEM"},
    {"id": "modis", "name": "MODIS NDVI MOD13Q1", "origin": "nasa", "role": "fifth", "access": "earthdata", "native_res_m": 250, "cadence": "16 días", "priority": "P0", "token_env": "EARTHDATA_TOKEN", "license": _NASA, "citation": "NASA LP DAAC, MOD13Q1"},
    {"id": "smap", "name": "SMAP L4", "origin": "nasa", "role": "trimmable", "access": "earthdata", "native_res_m": 9_000, "cadence": "3 horas", "priority": "P0", "token_env": "EARTHDATA_TOKEN", "license": _NASA, "citation": "NASA NSIDC, SMAP L4"},
    {"id": "ecostress", "name": "ECOSTRESS", "origin": "nasa", "role": "trimmable", "access": "earthdata", "native_res_m": 70, "cadence": "irregular", "priority": "P0", "token_env": "EARTHDATA_TOKEN", "license": _NASA, "citation": "NASA JPL/LP DAAC, ECOSTRESS"},
    {"id": "grace", "name": "GRACE / GRACE-FO", "origin": "nasa", "role": "trimmable", "access": "earthdata", "native_res_m": 300_000, "cadence": "mensual", "priority": "P1", "token_env": "EARTHDATA_TOKEN", "license": _NASA, "citation": "NASA JPL/PO.DAAC, GRACE/GRACE-FO"},
    {"id": "openmeteo", "name": "Open-Meteo archivo (ERA5)", "origin": "external", "role": "contrast", "access": "open", "native_res_m": 25_000, "cadence": "daily", "priority": "proposal", "token_env": None, "license": "CC BY 4.0 (Open-Meteo)", "citation": "Open-Meteo.com; datos ERA5 de Copernicus/ECMWF"},
    {"id": "soilgrids", "name": "SoilGrids", "origin": "external", "role": "complement", "access": "open", "native_res_m": 250, "cadence": "estático", "priority": "proposal", "token_env": None, "license": "CC BY 4.0 (ISRIC)", "citation": "Poggio et al. 2021, SoilGrids 2.0, SOIL 7"},
    {"id": "s2_earthsearch", "name": "Sentinel-2 L2A (Earth Search)", "origin": "external", "role": "backup", "access": "open", "native_res_m": 10, "cadence": "5 días", "priority": "proposal", "token_env": None, "license": "Copernicus Sentinel data (libre)", "citation": "Contains modified Copernicus Sentinel data; Element 84 Earth Search"},
    {"id": "hls_ndvi", "name": "HLS NDVI de la parcela (píxeles)", "origin": "nasa", "role": "derived", "access": "earthdata", "native_res_m": 30, "cadence": "2 a 3 días", "priority": "P0", "token_env": "EARTHDATA_TOKEN", "license": _NASA, "citation": "NASA LP DAAC, HLS v2.0"},
    {"id": "era5land", "name": "ERA5-Land (CDS)", "origin": "external", "role": "contrast", "access": "cds", "native_res_m": 9_000, "cadence": "horaria", "priority": "proposal", "token_env": "CDS_API_KEY", "license": "Términos de Copernicus CDS (revisar antes de usar)", "citation": "Copernicus Climate Change Service, ERA5-Land"},
]

BY_ID: dict[str, dict[str, Any]] = {s["id"]: s for s in SOURCES}
CORE = [s["id"] for s in SOURCES if s["role"] == "core"]


def rows() -> list[dict[str, Any]]:
    """El catálogo con el nivel de soporte calculado (es lo que se exporta a sources.json)."""
    return [{**s, "support": support_level(s["native_res_m"])} for s in SOURCES]
