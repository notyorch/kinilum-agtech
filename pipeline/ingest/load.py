"""Ejecuta cada conector y fija su estado: ok · pending (por integrar) · no_data (sin dato).

Una fuente que falla no detiene a las demás. Por cada fuente deja `manifest.json` en bronce
(`<data>/bronze/<parcela>/<fuente>/`) junto a las respuestas guardadas, como pide ingest/README.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import credentialed, imerg, nasadem, openmeteo, power, smap, soilgrids, stac
from .catalog import BY_ID, SOURCES
from .contract import STATUS_NO_DATA, STATUS_OK, STATUS_PENDING, Fetch, SourceError, SourcePending, now_utc
from .env import secret
from .http import Client


@dataclass(frozen=True)
class Params:
    lon: float
    lat: float
    start: str
    end: str
    plot_side_m: float = 200
    workers: int = 4  # peticiones simultáneas a IMERG y SMAP: pocas, por cortesía con el servidor
    smap_days: int = 365  # SMAP: solo los últimos N días del periodo (un granulo por día)


@dataclass
class Result:
    id: str
    status: str
    detail: str
    fetch: Fetch | None = None


def _token() -> str:
    tok = secret("EARTHDATA_TOKEN")
    if not tok:
        raise SourcePending("falta EARTHDATA_TOKEN")
    return tok


def smap_window(p: Params) -> tuple[str, str]:
    """El periodo de SMAP: los últimos `smap_days` días del periodo pedido (nunca antes de su inicio)."""
    first = max(np.datetime64(p.start), np.datetime64(p.end) - np.timedelta64(p.smap_days - 1, "D"))
    return str(first), p.end


CONNECTORS: dict[str, Callable[[Client, Params], Fetch]] = {
    "power": lambda c, p: power.fetch_power(c, p.lon, p.lat, p.start, p.end),
    "openmeteo": lambda c, p: openmeteo.fetch_openmeteo(c, p.lon, p.lat, p.start, p.end),
    "soilgrids": lambda c, p: soilgrids.fetch_soilgrids(c, p.lon, p.lat),
    "hls_stac": lambda c, p: stac.fetch_hls_scenes(c, p.lon, p.lat, p.start, p.end, p.plot_side_m),
    "s2_earthsearch": lambda c, p: stac.fetch_s2_scenes(c, p.lon, p.lat, p.start, p.end, p.plot_side_m),
    "imerg": lambda c, p: imerg.fetch_imerg(c, p.lon, p.lat, p.start, p.end, token=_token(), workers=p.workers),
    "nasadem": lambda c, p: nasadem.fetch_nasadem(c, p.lon, p.lat, p.plot_side_m, token=_token()),
    "modis": lambda c, p: credentialed.fetch_modis(c, p),
    "smap": lambda c, p: smap.fetch_smap(c, p.lon, p.lat, smap_window(p)[0], smap_window(p)[1], token=_token(), workers=p.workers),
    "ecostress": lambda c, p: credentialed.fetch_ecostress(c, p),
    "grace": lambda c, p: credentialed.fetch_grace(c, p),
    "era5land": lambda c, p: credentialed.fetch_era5land(c, p),
}


def run_one(client: Client, source_id: str, params: Params) -> Result:
    try:
        fetch = CONNECTORS[source_id](client, params)
        return Result(source_id, STATUS_OK, "; ".join(fetch.notes), fetch)
    except SourcePending as e:
        return Result(source_id, STATUS_PENDING, str(e))
    except SourceError as e:
        return Result(source_id, STATUS_NO_DATA, str(e)[:240])
    except Exception as e:  # una fuente rota no detiene a las demás
        return Result(source_id, STATUS_NO_DATA, f"inesperado: {type(e).__name__}: {str(e)[:200]}")


def write_manifest(directory: Path, parcel_id: str, params: Params, result: Result, files: list[str]) -> Path:
    prov = result.fetch.prov if result.fetch else None
    manifest = {
        "source": prov.source if prov else BY_ID[result.id]["name"],
        "product": prov.product if prov else None,
        "parcel": parcel_id,
        "requested": {"start": params.start, "end": params.end},
        "retrieved_at": prov.requested_at if prov else now_utc(),
        "status": result.status,
        "files": sorted(set(files)),
        "notes": [result.detail] if result.detail else [],
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_sources(
    client: Client,
    params: Params,
    *,
    enabled: list[str] | None = None,
    bronze_dir: Path | None = None,
    parcel_id: str = "yuc-demo-001",
) -> dict[str, Result]:
    unknown = set(enabled or []) - set(BY_ID)
    if unknown:
        raise ValueError(f"fuentes que no están en el catálogo: {', '.join(sorted(unknown))}")
    results: dict[str, Result] = {}
    for src in SOURCES:
        if enabled is not None and src["id"] not in enabled:
            continue
        folder = bronze_dir / parcel_id / src["id"] if bronze_dir else None
        client.cache_dir, client.used = folder, []
        result = run_one(client, src["id"], params)
        if folder:
            write_manifest(folder, parcel_id, params, result, client.used)
        results[src["id"]] = result
    return results
