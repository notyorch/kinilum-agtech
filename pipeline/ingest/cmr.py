"""Descubrimiento de productos de la NASA en CMR (abierto, sin credencial).

Los identificadores y versiones cambian (HLS pasó de HLSL30.v2.0 a HLSL30_2.0): se descubren, no se fijan.
"""

from __future__ import annotations

from typing import Any

from .http import Client

URL = "https://cmr.earthdata.nasa.gov/search/collections.json"


def find_collections(client: Client, keyword: str, n: int = 8) -> list[dict[str, Any]]:
    body = client.get_json(URL, params={"keyword": keyword, "page_size": n}).body
    return [
        {
            "short_name": e.get("short_name"),
            "version": e.get("version_id"),
            "title": e.get("title"),
            "provider": e.get("data_center"),
            "start": e.get("time_start"),
        }
        for e in body.get("feed", {}).get("entry", [])
    ]
