"""Escenas de satélite por STAC: HLS (CMR-STAC, NASA) y Sentinel-2 (Earth Search, respaldo). Solo metadatos.

Devuelve qué escenas existen y cuántas nubes traen; los píxeles (NDVI) se descargan con el token de Earthdata
y todavía no están integrados.

Dos cuidados:
  - CMR-STAC publica los índices de vegetación (`HLSL30_VI_2.0`, `HLSS30_VI_2.0`) como colecciones aparte, con
    las MISMAS escenas. Se piden solo las colecciones de reflectancia; si no, cada escena cuenta dos veces.
  - El listado de colecciones y los resultados vienen paginados: se sigue el enlace `next`.
  - CMR-STAC responde 502 cuando la página pesa más de ~1 MB (cada escena ocupa ~12 KB): con `limit=100` ya falla y
    con 75 responde. Se piden 50 por página. Earth Search tolera 200.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from .contract import Fetch, Provenance, SourceError, combined_sha, plot_bbox
from .http import Client

CMR_STAC = "https://cmr.earthdata.nasa.gov/stac/LPCLOUD"
EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"
_HLS_REFLECTANCE = re.compile(r"^HLS[LS]30([_.]|$)")
HLS_PAGE_LIMIT = 50
S2_PAGE_LIMIT = 200
MAX_PAGES = 100  # 50 por página → 5,000 escenas: diez años de dos productos caben con holgura


def parse_datetime(text: str) -> datetime:
    """ISO 8601 con o sin fracción de segundo y con `Z`: los servicios mezclan formatos."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def scene_key(scene_id: str) -> str:
    """Clave de una escena sin el prefijo del producto: HLS.L30.T16QBH… y HLS-VI.L30.T16QBH… son la misma escena."""
    return scene_id.split(".", 1)[1] if scene_id.startswith("HLS") and "." in scene_id else scene_id


def hls_collection_ids(client: Client, max_pages: int = 10) -> list[str]:
    """Colecciones HLS de reflectancia (L30 y S30), versión 2.0 si hay varias; sin las de índices (VI)."""
    ids: list[str] = []
    url, params = f"{CMR_STAC}/collections", {"limit": 200}
    for _ in range(max_pages):
        body = client.get_json(url, params=params).body
        ids += [c["id"] for c in body.get("collections", []) if _HLS_REFLECTANCE.match(c["id"]) and "VI" not in c["id"]]
        nxt = next((link for link in body.get("links", []) if link.get("rel") == "next"), None)
        if not nxt:
            break
        url, params = nxt["href"], None
    v2 = sorted(i for i in set(ids) if "2.0" in i)
    return v2 or sorted(set(ids))


def search(
    client: Client, base: str, collections: list[str], bbox: list[float], start: str, end: str, *, limit: int, max_pages: int = MAX_PAGES
) -> tuple[list[dict[str, Any]], str, bool]:
    """Escenas que cruzan el rectángulo: [{id, collection, datetime, cloud}], huella de la respuesta y si se cortó."""
    method, url = "POST", f"{base}/search"
    payload: Any = {"collections": collections, "bbox": bbox, "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": limit}
    scenes: list[dict[str, Any]] = []
    shas: list[str] = []
    pages = 0
    while url and pages < max_pages:
        r = client.get_json(url, method=method, body=payload)
        shas.append(r.sha256)
        pages += 1
        for f in r.body.get("features", []):
            props = f.get("properties", {})
            if not props.get("datetime"):
                continue
            scenes.append(
                {"id": f["id"], "collection": f.get("collection"), "datetime": parse_datetime(props["datetime"]), "cloud": props.get("eo:cloud_cover")}
            )
        nxt = next((link for link in r.body.get("links", []) if link.get("rel") == "next"), None)
        if nxt:
            method, url, payload = nxt.get("method", "GET"), nxt["href"], nxt.get("body")
        else:
            url = None
    return scenes, combined_sha(shas), pages >= max_pages and url is not None


def unique_scenes(scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for s in scenes:
        k = scene_key(s["id"])
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out


def fetch_hls_scenes(client: Client, lon: float, lat: float, start: str, end: str, side_m: float = 200) -> Fetch:
    ids = hls_collection_ids(client)
    if not ids:
        raise SourceError("CMR-STAC no devolvió colecciones HLS")
    bbox = plot_bbox(lon, lat, side_m)
    scenes, sha, cut = search(client, CMR_STAC, ids, bbox, start, end, limit=HLS_PAGE_LIMIT)
    uniq = unique_scenes(scenes)
    prov = Provenance(
        "HLS (NASA LP DAAC)",
        "+".join(ids),
        f"{CMR_STAC}/search",
        {"bbox": bbox, "start": start, "end": end},
        response_sha256=sha,
        license="Datos abiertos NASA",
        citation="NASA LP DAAC, HLS v2.0",
    )
    notes = ["Solo metadatos de escenas; sin píxeles."]
    if len(uniq) != len(scenes):
        notes.append(f"{len(scenes) - len(uniq)} escenas repetidas descartadas")
    if cut:
        notes.append("Paginación cortada en max_pages")
    return Fetch(uniq, prov, notes=notes)


def fetch_s2_scenes(client: Client, lon: float, lat: float, start: str, end: str, side_m: float = 200) -> Fetch:
    bbox = plot_bbox(lon, lat, side_m)
    scenes, sha, cut = search(client, EARTH_SEARCH, ["sentinel-2-l2a"], bbox, start, end, limit=S2_PAGE_LIMIT)
    prov = Provenance(
        "Sentinel-2 L2A (Earth Search)",
        "sentinel-2-l2a",
        f"{EARTH_SEARCH}/search",
        {"bbox": bbox, "start": start, "end": end},
        response_sha256=sha,
        license="Copernicus Sentinel data (libre)",
        citation="Contains modified Copernicus Sentinel data; Element 84 Earth Search",
    )
    return Fetch(unique_scenes(scenes), prov, notes=["Solo metadatos de escenas; sin píxeles."] + (["Paginación cortada en max_pages"] if cut else []))
