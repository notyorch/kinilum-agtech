"""NDVI de la parcela en todas las escenas de HLS, con Sentinel-2 como respaldo de los meses sin escena despejada.

Depende de las escenas que ya trajo `hls_stac` (y `s2_earthsearch`): ese paso solo lista; este lee los píxeles. Solo se
usan las escenas del mosaico de la zona UTM del punto, y de ellas las de nubosidad moderada (la nubosidad del metadato es
la de todo el mosaico de 110 km; lo que importa es la de la parcela, que decide la máscara de cada escena).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

from .contract import Fetch, Provenance, SourceError, combined_sha
from .http import Client
from .vegetation import Observation, observe_hls, observe_many, observe_s2

CLOUD_PREFILTER = 70  # % de nubes del mosaico; por encima casi nunca queda un píxel despejado (propuesta)
S2_CLOUD_MAX = 30  # el respaldo solo mira escenas de Sentinel-2 poco nubladas
S2_TRIES_PER_MONTH = 3


def utm_zone(lon: float) -> int:
    return int((lon + 180) // 6) + 1


def _tile(scene_id: str) -> str:
    return scene_id.split(".")[2] if scene_id.startswith("HLS") else ""


def _months(start: str, end: str) -> list[str]:
    return [str(m) for m in np.arange(np.datetime64(start[:7], "M"), np.datetime64(end[:7], "M") + np.timedelta64(1, "M"))]


def fetch_cover(client: Client, hls_scenes: list[dict[str, Any]], s2_scenes: list[dict[str, Any]] | None, lon: float, lat: float,
                start: str, end: str, *, token: str, side_m: float = 200, workers: int = 4) -> Fetch:
    zone = utm_zone(lon)
    scenes = [s for s in hls_scenes if _tile(s["id"]).startswith(f"T{zone:02d}") and (s["cloud"] is None or s["cloud"] <= CLOUD_PREFILTER)]
    if not scenes:
        raise SourceError(f"no hay escenas de HLS del mosaico de la zona {zone} con nubosidad de {CLOUD_PREFILTER} % o menos")
    obs, errors = observe_many(lambda s: observe_hls(client, s, lon, lat, token, side_m), scenes, workers)
    if not obs:
        raise SourceError(f"ninguna escena de HLS se pudo leer: {errors[0] if errors else 'sin detalle'}")

    have = {o.date.strftime("%Y-%m") for o in obs if np.isfinite(o.ndvi)}
    missing = [m for m in _months(start, end) if m not in have]
    s2_used = 0
    if s2_scenes and missing:
        # El respaldo: por cada mes sin escena despejada de HLS, las escenas de Sentinel-2 menos nubladas, hasta que una sirva.
        by_month: dict[str, list[dict[str, Any]]] = {}
        for s in s2_scenes:
            if s["cloud"] is not None and s["cloud"] <= S2_CLOUD_MAX and s.get("epsg") in (None, 32600 + zone):
                by_month.setdefault(s["datetime"].strftime("%Y-%m"), []).append(s)

        def month(m: str) -> tuple[list[Observation], list[str]]:
            got: list[Observation] = []
            errs: list[str] = []
            for s in sorted(by_month.get(m, []), key=lambda x: x["cloud"])[:S2_TRIES_PER_MONTH]:
                try:
                    o = observe_s2(client, s, lon, lat, side_m)
                except SourceError as e:
                    errs.append(f"{s['id']}: {e}")
                    continue
                if np.isfinite(o.ndvi):
                    got.append(o)
                    break
            return got, errs

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for got, errs in pool.map(month, missing):
                obs += got
                s2_used += len(got)
                errors += errs

    clear = [o for o in obs if np.isfinite(o.ndvi)]
    prov = Provenance(
        "HLS (NASA LP DAAC)", "HLSL30 + HLSS30 v2.0, NDVI de los píxeles limpios de la parcela", "https://data.lpdaac.earthdatacloud.nasa.gov (GeoTIFF por rangos)",
        {"lon": lon, "lat": lat, "start": start, "end": end, "side_m": side_m, "zone": zone},
        response_sha256=combined_sha(sorted(f"{o.scene}:{o.ndvi:.6f}" for o in obs)),
        license="Datos abiertos NASA", citation="NASA LP DAAC, HLS v2.0; respaldo: Contains modified Copernicus Sentinel data, Element 84 Earth Search",
    )
    n_hls = len([o for o in clear if o.sensor != "S2"])
    notes = [f"{len(scenes)} escenas de HLS leídas; {n_hls} con la parcela despejada y {len(obs) - len(clear)} con nubes sobre ella"]
    if s2_used:
        notes.append(f"{s2_used} meses completados con Sentinel-2 (respaldo)")
    if errors:
        notes.append(f"{len(errors)} escenas que no se pudieron leer ({errors[0][:100]})")
    return Fetch(sorted(obs, key=lambda o: o.date), prov, {"ndvi": "1"}, notes)
