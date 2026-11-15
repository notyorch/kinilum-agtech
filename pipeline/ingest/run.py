"""Pide las fuentes, deja bronce con su manifiesto y escribe el informe del EDA.

    python -m ingest.run --lon -89.42 --lat 20.30 [--parcel yuc-demo-001] [--start 2016-01-01 --end 2025-12-31]
                         [--plot-side-m 200] [--only power,openmeteo] [--data-dir pipeline/data]

El punto es obligatorio: el polígono de la parcela de ejemplo aún no está elegido y nadie lo inventa aquí.
Las credenciales se leen de EARTHDATA_TOKEN, CDS_API_KEY e INEGI_TOKEN; sin ellas esas fuentes quedan «por integrar».
Una segunda corrida sale de la caché y no vuelve a pedir nada.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common.schema import REPO

from . import catalog
from .eda import build_report
from .http import Client
from .load import Params, load_sources

LABEL = {"ok": "ok", "pending": "por integrar", "no_data": "sin dato"}


def to_markdown(report: dict, parcel: str, results: dict) -> str:
    lines = [f"# Informe EDA · {parcel}", "", f"Decisión de entrega: **{report['decision_entrega']}**", "", "## Fuentes", ""]
    lines += [f"- {k}: {LABEL[r.status]}" + (f" ({r.detail})" if r.detail else "") for k, r in results.items()]
    lines += ["", "## Avisos", ""] + ([f"- {w}" for w in report["warnings"]] or ["- ninguno"])
    lines += ["", "## Decisiones de degradación", ""] + [f"- {d['fuente']}: {d['accion']} · aviso: {d['aviso_en_pantalla']}" for d in report["decisions"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parcel", default="yuc-demo-001")
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--plot-side-m", type=float, default=200)
    ap.add_argument("--elev-m", type=float, default=40.0, help="supuesto hasta integrar NASADEM")
    ap.add_argument("--only", help="fuentes separadas por coma (por defecto, todas las del catálogo)")
    ap.add_argument("--data-dir", type=Path, default=REPO / "pipeline" / "data")
    args = ap.parse_args(argv)

    params = Params(args.lon, args.lat, args.start, args.end, args.plot_side_m)
    only = args.only.split(",") if args.only else None
    client = Client()
    results = load_sources(client, params, enabled=only, bronze_dir=args.data_dir / "bronze", parcel_id=args.parcel)
    report = build_report(results, params, elev_m=args.elev_m)

    out = args.data_dir / "eda" / args.parcel
    out.mkdir(parents=True, exist_ok=True)
    (out / "eda_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str, allow_nan=False) + "\n", encoding="utf-8")
    (out / "eda_report.md").write_text(to_markdown(report, args.parcel, results), encoding="utf-8")
    (out / "sources.json").write_text(json.dumps(catalog.rows(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(to_markdown(report, args.parcel, results))
    print(f"Peticiones reales: {client.calls}. Archivos en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
