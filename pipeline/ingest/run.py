"""Pide las fuentes, deja bronce con su manifiesto y escribe el informe del EDA.

    python -m ingest.run --lon -89.42 --lat 20.30 [--parcel sin-demo-001] [--start 2016-01-01 --end 2025-12-31]
                         [--plot-side-m 200] [--only power,openmeteo] [--data-dir pipeline/data]

El punto es obligatorio: el polígono de la parcela de ejemplo aún no está elegido y nadie lo inventa aquí.
Las credenciales se leen de EARTHDATA_TOKEN, CDS_API_KEY e INEGI_TOKEN; sin ellas esas fuentes quedan «por integrar».
Una segunda corrida sale de la caché y no vuelve a pedir nada.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from common.schema import REPO
from harmonize.cover import green_cover_json
from harmonize.values import context_values, partial_values
from harmonize.season import gold_parts

from package.build import BuildError, load_config

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
    ap.add_argument("--parcel", default="sin-demo-001")
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--plot-side-m", type=float, default=200)
    ap.add_argument("--elev-m", type=float, default=40.0, help="elevación supuesta; solo se usa si NASADEM no llegó")
    ap.add_argument("--soil-fallback-m", type=int, default=1000, help="si SoilGrids no tiene valores en el punto, busca la celda válida más cercana hasta este radio en metros (0 lo apaga)")
    ap.add_argument("--workers", type=int, default=4, help="peticiones simultáneas a IMERG (pocas, por cortesía con el servidor)")
    ap.add_argument("--only", help="fuentes separadas por coma (por defecto, todas las del catálogo)")
    ap.add_argument("--data-dir", type=Path, default=REPO / "pipeline" / "data")
    args = ap.parse_args(argv)

    params = Params(args.lon, args.lat, args.start, args.end, args.plot_side_m, args.workers, soil_fallback_m=args.soil_fallback_m)
    only = args.only.split(",") if args.only else None
    client = Client()
    results = load_sources(client, params, enabled=only, bronze_dir=args.data_dir / "bronze", parcel_id=args.parcel)
    report = build_report(results, params, elev_m=args.elev_m)

    out = args.data_dir / "eda" / args.parcel
    out.mkdir(parents=True, exist_ok=True)
    (out / "eda_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str, allow_nan=False) + "\n", encoding="utf-8")
    (out / "eda_report.md").write_text(to_markdown(report, args.parcel, results), encoding="utf-8")
    (out / "sources.json").write_text(json.dumps(catalog.rows(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    try:
        config = load_config(args.parcel)  # lo que declara el técnico: de ahí sale `soil`
    except BuildError:
        config = None
    values = partial_values(results, config, date.today().isoformat())
    context = context_values(results)
    if values:
        gold = args.data_dir / "gold" / args.parcel
        gold.mkdir(parents=True, exist_ok=True)
        missing = [k for k in ("rain", "bare", "heat", "soil", "moisture", "slope") if k not in values]
        note = ("COMPLETO: los seis valores del contrato. No es todavía el paquete: faltan las demás partes del oro." if not missing
                else "PARCIAL: solo los valores que ya tienen fuente. Faltan " + ", ".join(missing) + ". No es el values.json del paquete.")
        doc = {"_nota": note, "values": values, "context": context}
        (gold / ("values.json" if not missing else "values.partial.json")).write_text(json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
        if "hls_ndvi" in results and results["hls_ndvi"].fetch:
            (gold / "green_cover.json").write_text(json.dumps(green_cover_json(results["hls_ndvi"].fetch), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        if config is not None:
            parts, why = gold_parts(results, config, args.lat, args.lon)
            for name, content in parts.items():
                (gold / name).write_text(json.dumps(content, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
            for line in why:
                print(f"oro: {line}")

    print(to_markdown(report, args.parcel, results))
    print(f"Peticiones reales: {client.calls}. Archivos en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
