"""Acceso a los datos de la NASA con token de Earthdata: IMERG, NASADEM, MODIS y HLS.

Para cada producto: (1) busca en CMR, que es abierto, un granulo que cruce la parcela; (2) pide el principio de su
archivo con `Authorization: Bearer`; (3) comprueba que lo recibido ES el archivo (por su firma de formato) y no la
página de inicio de sesión, que también responde 200. Cada prueba se repite SIN token como control: si sin token
también «funciona», el token no demuestra nada.

No es todavía el conector: confirma que hay acceso. Leer el valor del punto es el siguiente paso.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contract import SourceError, plot_bbox
from .http import Client, Once, Probe, fetch_prefix

CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.json"
DATA_REL = "/data#"


@dataclass(frozen=True)
class Product:
    key: str
    name: str
    short_name: str
    version: str
    query: dict[str, str]  # filtros de CMR (fechas, nubes)
    suffix: str  # qué archivo del granulo se prueba
    magic: tuple[bytes, ...]  # primeros bytes de ese formato


PRODUCTS: dict[str, Product] = {
    "imerg": Product("imerg", "GPM IMERG Final diario", "GPM_3IMERGDF", "07",
                     {"temporal": "2025-01-01T00:00:00Z,2025-01-01T23:59:59Z"}, ".nc4", (b"\x89HDF",)),
    "nasadem": Product("nasadem", "NASADEM", "NASADEM_HGT", "001", {}, ".zip", (b"PK\x03\x04",)),
    "modis": Product("modis", "MODIS NDVI MOD13Q1", "MOD13Q1", "061",
                     {"temporal": "2025-01-01T00:00:00Z,2025-01-16T23:59:59Z"}, ".hdf", (b"\x0e\x03\x13\x01",)),
    "hls": Product("hls", "HLS Landsat (banda roja B04)", "HLSL30", "2.0",
                   {"temporal": "2025-03-01T00:00:00Z,2025-04-30T23:59:59Z", "cloud_cover": "0,30"}, ".B04.tif",
                   (b"II*\x00", b"MM\x00*", b"II+\x00")),
}


def find_granule(client: Client, product: Product, bbox: list[float]) -> dict[str, Any]:
    """Un granulo del producto que cruza el rectángulo, con el enlace de datos del archivo a probar."""
    params = {"short_name": product.short_name, "version": product.version, "page_size": 1,
              "bounding_box": ",".join(f"{x:.6f}" for x in bbox), **product.query}
    entries = client.get_json(CMR_GRANULES, params=params).body.get("feed", {}).get("entry", [])
    if not entries:
        raise SourceError(f"CMR no tiene granulos de {product.short_name} {product.version} para ese punto y esas fechas")
    entry = entries[0]
    urls = [link["href"] for link in entry.get("links", [])
            if link.get("rel", "").endswith(DATA_REL) and link["href"].startswith("https://") and link["href"].split("?")[0].endswith(product.suffix)]
    if not urls:
        raise SourceError(f"el granulo {entry.get('title')} no trae un archivo {product.suffix}")
    return {"title": entry.get("title"), "size_mb": _megabytes(entry.get("granule_size")), "url": urls[0]}


def _megabytes(value: Any) -> float | None:
    """CMR entrega `granule_size` como texto («26.75») y a veces no lo entrega."""
    try:
        return round(float(value), 1)
    except (TypeError, ValueError):
        return None


def verdict(product: Product, probe: Probe) -> tuple[str, str]:
    """(veredicto, detalle): «acceso», «sin acceso» o «error». Un 200 que no es el archivo no cuenta como acceso."""
    if probe.error:
        return "error", probe.error
    if probe.status in (200, 206) and any(probe.data.startswith(m) for m in product.magic):
        return "acceso", f"{probe.status}, {len(probe.data)} bytes y firma de formato correcta"
    if probe.status in (401, 403):
        return "sin acceso", f"HTTP {probe.status}"
    if probe.status in (200, 206):
        return "sin acceso", "respondió 200 pero no es el archivo (¿página de inicio de sesión?)"
    return "error", f"HTTP {probe.status}"


def check_product(client: Client, product: Product, token: str, bbox: list[float], *, nbytes: int = 65_536, once: Once | None = None) -> dict[str, Any]:
    """Prueba un producto con token y, de control, sin token."""
    row: dict[str, Any] = {"producto": product.key, "nombre": product.name, "short_name": product.short_name, "version": product.version}
    try:
        granule = find_granule(client, product, bbox)
    except SourceError as e:
        return {**row, "veredicto": "error", "detalle": str(e)}
    row.update(granulo=granule["title"], tamano_mb=granule["size_mb"])
    for label, tok in (("con_token", token), ("sin_token", None)):
        probe = fetch_prefix(granule["url"], token=tok, nbytes=nbytes, once=once)
        v, detail = verdict(product, probe)
        row[label] = {"veredicto": v, "detalle": detail, "estado_http": probe.status, "bytes_recibidos": len(probe.data),
                      "tamano_total_bytes": probe.total_bytes, "saltos": probe.hops, "token_en_saltos": probe.token_hops, "destino": probe.final}
    row["veredicto"] = row["con_token"]["veredicto"]
    return row


def check_access(client: Client, token: str, lon: float, lat: float, *, side_m: float = 200, only: list[str] | None = None,
                 nbytes: int = 65_536, once: Once | None = None) -> list[dict[str, Any]]:
    unknown = set(only or []) - set(PRODUCTS)
    if unknown:
        raise ValueError(f"productos desconocidos: {', '.join(sorted(unknown))}")
    bbox = plot_bbox(lon, lat, side_m)
    return [check_product(client, p, token, bbox, nbytes=nbytes, once=once) for k, p in PRODUCTS.items() if only is None or k in only]
