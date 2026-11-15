"""Comprueba el acceso a IMERG, NASADEM, MODIS y HLS con el token de Earthdata.

    python -m ingest.access [--lon -89.42 --lat 20.30] [--only imerg,hls] [--bytes 65536]

Lee EARTHDATA_TOKEN de la variable de entorno o del `.env` (que git ignora). Descarga solo el principio de un
archivo por producto y repite la prueba sin token como control. Nunca imprime ni guarda el token. Deja
`data/access/access_report.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common.schema import REPO

from .earthdata import PRODUCTS, check_access
from .env import secret
from .http import Client


def render(rows: list[dict]) -> str:
    out = []
    for r in rows:
        out.append(f"{r['nombre']} ({r['short_name']} {r['version']})")
        if "con_token" not in r:
            out += [f"   {r['veredicto'].upper()}: {r['detalle']}", ""]
            continue
        size = f" ({r['tamano_mb']} MB)" if r.get("tamano_mb") else ""
        out.append(f"   granulo {r['granulo']}{size}")
        for label, key in (("con token", "con_token"), ("sin token", "sin_token")):
            c = r[key]
            total = f", archivo de {c['tamano_total_bytes'] / 1e6:.1f} MB" if c["tamano_total_bytes"] else ""
            out.append(f"   {label}: {c['veredicto'].upper()} · {c['detalle']}{total} · saltos: {' → '.join(c['saltos'])}")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lon", type=float, default=-89.42)
    ap.add_argument("--lat", type=float, default=20.30)
    ap.add_argument("--only", help=f"productos separados por coma: {', '.join(PRODUCTS)}")
    ap.add_argument("--bytes", type=int, default=65_536, help="cuántos bytes pedir de cada archivo")
    ap.add_argument("--data-dir", type=Path, default=REPO / "pipeline" / "data")
    args = ap.parse_args(argv)

    token = secret("EARTHDATA_TOKEN")
    if not token:
        print("Falta EARTHDATA_TOKEN: póngalo en la variable de entorno o en el .env de la raíz (git lo ignora).", file=sys.stderr)
        return 2
    out = args.data_dir / "access"
    client = Client(out / "_cache")
    rows = check_access(client, token, args.lon, args.lat, only=args.only.split(",") if args.only else None, nbytes=args.bytes)
    out.mkdir(parents=True, exist_ok=True)
    (out / "access_report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(render(rows))
    ok = [r["producto"] for r in rows if r["veredicto"] == "acceso"]
    print(f"Con acceso: {', '.join(ok) or 'ninguno'} · sin acceso o con error: {', '.join(r['producto'] for r in rows if r['veredicto'] != 'acceso') or 'ninguno'}")
    return 0 if len(ok) == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
