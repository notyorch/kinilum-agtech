"""Paso 4 del pipeline: arma, valida y publica el paquete de una parcela (oro → app/public/packages/).

    python -m package.build --parcel sin-demo-001 [--date AAAA-MM-DD] [--out app/public/packages]

Entradas:
  - pipeline/parcels/<id>.yaml            lo que declara el técnico (shared/schema: ParcelConfig)
  - pipeline/data/gold/<id>/*.json        lo que dejan los pasos anteriores (ver README.md)

Reglas:
  - Si el paquete no pasa el esquema y las comprobaciones, NO se escribe nada.
  - El nombre del archivo lleva parcela y fecha (<id>.<fecha>.json; el mismo día, .r2, .r3…): un
    paquete nuevo nunca se confunde con uno viejo en la caché del celular. Si el contenido es idéntico
    al ya publicado ese día, no se vuelve a escribir.
  - El polígono exacto NO entra: el paquete lleva solo un punto redondeado a 2 decimales y las hectáreas.
  - El paquete lleva solo la variante de frijol elegida (`rotation.E2.variant`). Cambiarla cambia el
    contenido y, por lo tanto, el nombre del archivo.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from common.schema import REPO, schema_errors
from package.validate import PACKAGES_DIR, package_problems
from simulate.crops import rotation_block

PIPELINE = REPO / "pipeline"
PACKAGE_FORMAT = "kinilum-package/2"

# Partes del oro que el paquete necesita (nombre de archivo → clave del paquete).
REQUIRED_PARTS = {
    "values.json": "values",
    "rain_this_season.json": "rain_this_season",
    "green_cover.json": "green_cover",
    "seasons.json": "seasons",
    "thresholds.json": "thresholds",
}
OPTIONAL_PARTS = {
    "normals.json": "normals",
    "map_30m.json": "map_30m",
    "simulation.json": "simulation",
}


class BuildError(Exception):
    """Algo impide armar el paquete; el mensaje dice qué y cómo arreglarlo."""


def load_config(parcel_id: str) -> dict[str, Any]:
    path = PIPELINE / "parcels" / f"{parcel_id}.yaml"
    if not path.exists():
        raise BuildError(f"no existe {path.relative_to(REPO)}")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = schema_errors("parcel-config", config)
    if errors:
        raise BuildError("la configuración de la parcela no cumple el esquema:\n  " + "\n  ".join(errors))
    if config["id"] != parcel_id:
        raise BuildError(f"{path.name}: el id ({config['id']}) no coincide con el nombre del archivo")
    return config


def polygon_area_ha(ring: list[list[float]]) -> float:
    """Área aproximada en hectáreas (proyección local plana; error de ~1 % en una parcela)."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    lat0 = sum(p[1] for p in pts) / len(pts)
    kx, ky = 111_320 * math.cos(math.radians(lat0)), 110_574
    xy = [(p[0] * kx, p[1] * ky) for p in pts]
    twice = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(xy, xy[1:] + xy[:1]))
    return abs(twice) / 2 / 10_000


def reference_point(ring: list[list[float]]) -> list[float]:
    """[longitud, latitud] del centro, REDONDEADA a 2 decimales (≈ 1 km): ubica la zona, no la parcela."""
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    return [round(sum(p[0] for p in pts) / len(pts), 2), round(sum(p[1] for p in pts) / len(pts), 2)]


def load_gold(parcel_id: str) -> dict[str, Any]:
    gold = PIPELINE / "data" / "gold" / parcel_id
    parts: dict[str, Any] = {}
    missing = [f for f in REQUIRED_PARTS if not (gold / f).exists()]
    if missing:
        raise BuildError(
            f"faltan partes del oro en {gold.relative_to(REPO)}: {', '.join(missing)}. "
            "Las dejan los pasos anteriores (ingest → harmonize → simulate); ver pipeline/README.md."
        )
    for fname, key in {**REQUIRED_PARTS, **OPTIONAL_PARTS}.items():
        if (gold / fname).exists():
            parts[key] = json.loads((gold / fname).read_text(encoding="utf-8"))
    # `ingest.run` escribe values.json como {"_nota", "values", "context"}: al paquete solo entran los seis valores.
    if isinstance(parts.get("values"), dict) and "values" in parts["values"]:
        parts["values"] = parts["values"]["values"]
    meta_path = gold / "meta.json"
    if not meta_path.exists():
        raise BuildError(f"falta {meta_path.relative_to(REPO)} con {{\"clean_pixels\": n}} (cuadros limpios de 30 m)")
    parts["_meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
    return parts


def extreme_heat(parts: dict[str, Any]) -> bool | None:
    """¿La temperatura máxima de la zona alcanza el umbral de calor que daña? `None` si no hay dato."""
    value = parts.get("values", {}).get("heat", {}).get("value")
    threshold = parts.get("thresholds", {}).get("heat_c")
    if value is None or threshold is None:
        return None
    return value >= threshold


def assemble(config: dict[str, Any], parts: dict[str, Any], generated_at: str) -> dict[str, Any]:
    ring = config.get("polygon")
    pkg: dict[str, Any] = {
        "package_format": PACKAGE_FORMAT,
        "parcel_id": config["id"],
        "generated_at": generated_at,
        "illustrative": config["illustrative"],
        "area_ha": round(polygon_area_ha(ring), 1) if ring else config["area_ha"],
        "region_key": config["region_key"],
    }
    if ring:
        pkg["reference_point"] = reference_point(ring)
    pkg["clean_pixels"] = parts["_meta"]["clean_pixels"]
    for key in [*REQUIRED_PARTS.values(), "normals"]:
        if key in parts:
            pkg[key] = parts[key]
    pkg["restrictions"] = {k: config[k] for k in ("water", "machinery", "cultivos_aceptados", "market", "sowing", "soil")}
    heat = extreme_heat(parts)
    if heat is not None:
        pkg["restrictions"]["extreme_heat"] = heat
    try:
        # El paquete lleva solo la variante de frijol elegida, y quién la eligió.
        pkg["rotation"] = rotation_block(config.get("frijol_variante"), config.get("frijol_variante_elegida_por", "technician"))
    except ValueError as e:
        raise BuildError(str(e)) from e
    for key in ("map_30m", "simulation"):
        if key in parts:
            pkg[key] = parts[key]
    return pkg


def dumps(pkg: dict[str, Any]) -> str:
    """JSON compacto (el paquete pesa menos de 500 KB) y estable: el mismo contenido da los mismos bytes."""
    return json.dumps(pkg, ensure_ascii=False, separators=(",", ":"))


def next_filename(out: Path, parcel_id: str, day: str, text: str, previous: str | None = None) -> tuple[str, bool]:
    """(nombre, ya_existe_igual). Mismo día y otro contenido → .r2, .r3…

    `previous` es el archivo que hoy apunta el índice. Nunca se vuelve a un nombre anterior a ese,
    aunque haya quedado libre: un celular podría tener en caché el contenido viejo con ese nombre.
    """
    base = f"{parcel_id}.{day}"
    candidates = [f"{base}.json"] + [f"{base}.r{n}.json" for n in range(2, 100)]
    start = candidates.index(previous) if previous in candidates else 0
    for name in candidates[start:]:
        path = out / name
        if not path.exists():
            return name, False
        if path.read_text(encoding="utf-8") == text:
            return name, True
    raise BuildError("demasiadas revisiones el mismo día")


def publish(out: Path, pkg: dict[str, Any], text: str) -> str:
    """Escribe el paquete y actualiza index.json. Devuelve el nombre del archivo."""
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"parcels": {}}
    previous = index["parcels"].get(pkg["parcel_id"], {}).get("file")

    name, same = next_filename(out, pkg["parcel_id"], pkg["generated_at"], text, previous)
    if not same:
        (out / name).write_text(text, encoding="utf-8")
    index["parcels"][pkg["parcel_id"]] = {"file": name, "generated_at": pkg["generated_at"]}
    index["parcels"] = dict(sorted(index["parcels"].items()))
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # El paquete anterior de esta parcela ya nadie lo apunta: se quita para no dejarlo huérfano en dist/.
    if previous and previous != name and re.fullmatch(r"[A-Za-z0-9_-]+\.\d{4}-\d{2}-\d{2}(\.r\d+)?\.json", previous):
        (out / previous).unlink(missing_ok=True)
    return name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parcel", required=True)
    ap.add_argument("--date", default=date.today().isoformat(), help="fecha de generación AAAA-MM-DD (por defecto, hoy)")
    ap.add_argument("--out", type=Path, default=PACKAGES_DIR)
    args = ap.parse_args(argv)
    try:
        config = load_config(args.parcel)
        pkg = assemble(config, load_gold(args.parcel), args.date)
        text = dumps(pkg)
        problems = package_problems(json.loads(text), len(text.encode("utf-8")))
        if problems:
            raise BuildError("el paquete no pasa la validación y no se escribió:\n  " + "\n  ".join(problems))
        name = publish(args.out, pkg, text)
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"Paquete listo: {args.out / name} ({len(text.encode('utf-8')) / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
