"""Validación de un paquete: esquema JSON + las comprobaciones que el esquema no expresa.

    python -m package.validate                        valida todo app/public/packages/
    python -m package.validate ruta/paquete.json ...  valida los archivos dados

Repite las comprobaciones de app/scripts/check-schema.mjs: si cambia una, cambie la otra.
Un paquete que no pasa NO sale del pipeline (ARQUITECTURA-DEV §4.4).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import sys
from pathlib import Path
from typing import Any

from common.schema import REPO, schema_errors
from simulate.encode import NO_DATA
from simulate.scenarios import CRITERIA, NAMED, ROTATION_CROP, STRATEGIES, scenario_at

MAX_PACKAGE_BYTES = 500 * 1024
PACKAGES_DIR = REPO / "app" / "public" / "packages"
_FORBIDDEN_KEYS = re.compile(r'"(polygon|geometry|coordinates|lat|lon|lng|latitude|longitude)"\s*:')


def semantic_problems(pkg: dict[str, Any]) -> list[str]:
    """Lo que el esquema JSON no dice. Supone que el esquema ya pasó."""
    out: list[str] = []

    for key, v in pkg["values"].items():
        if v["value"] is not None and not (v["p10"] <= v["value"] <= v["p90"]):
            out.append(f"values.{key}: debe cumplirse p10 ≤ value ≤ p90 ({v['p10']}, {v['value']}, {v['p90']})")
    for i, p in enumerate(pkg["rain_this_season"]["projected"]):
        if not (p["lo"] <= p["y"] <= p["hi"]):
            out.append(f"rain_this_season.projected[{i}]: debe cumplirse lo ≤ y ≤ hi")
    for s in pkg["seasons"]:
        d = s["deficit"]
        if not (d["p10"] <= d["p50"] <= d["p90"]):
            out.append(f"seasons {s['year']}: deficit debe cumplir p10 ≤ p50 ≤ p90")

    # Privacidad (ARQUITECTURA-DEV §5.3): a lo más 2 decimales (≈ 1 km) en el punto de referencia.
    for n in pkg.get("reference_point", []):
        if abs(n * 100 - round(n * 100)) > 1e-9:
            out.append(f"reference_point: {n} tiene más de 2 decimales (ubicaría la parcela)")
    if _FORBIDDEN_KEYS.search(json.dumps(pkg, ensure_ascii=False)):
        out.append("el paquete lleva un campo de polígono o coordenadas: no se publica")

    m = pkg.get("map_30m")
    if m:
        cols = len(m["mask"][0])
        if any(len(row) != cols for row in m["mask"]):
            out.append("map_30m.mask: todas las filas deben medir lo mismo")
        clean = "".join(m["mask"]).count("c")
        if clean != pkg["clean_pixels"]:
            out.append(f"clean_pixels ({pkg['clean_pixels']}) no coincide con los cuadros «c» de la máscara ({clean})")
        for name, layer in m["layers"].items():
            if len(layer["values"]) != len(m["mask"]) or any(len(row) != cols for row in layer["values"]):
                out.append(f"map_30m.layers.{name}: las dimensiones no coinciden con la máscara")

    rotation = pkg.get("rotation")
    if rotation:
        for strategy, crop in ROTATION_CROP.items():
            if rotation[strategy]["rotation_crop"] != crop:
                out.append(f"rotation.{strategy}: rotation_crop debe ser {crop}, no {rotation[strategy]['rotation_crop']}")

    sim = pkg.get("simulation")
    if sim:
        if rotation and sim["rules_version"] != rotation["rules_version"]:
            out.append("simulation.rules_version no coincide con rotation.rules_version")
        # (estrategia, criterio) declarados sin dato: sus bytes valen 255 en todas las corridas.
        declared = {
            (STRATEGIES.index(s), CRITERIA.index(c)) for s, criteria in sim.get("no_data", {}).items() for c in criteria
        }
        seen: set[tuple[int, int]] = set()
        for i, c in enumerate(sim["cells"]):
            key = (c["rain"], c["temp"])
            label = f"simulation.cells[{i}] ({key[0]}/{key[1]})"
            if key in seen:
                out.append(f"{label}: celda repetida")
            seen.add(key)
            named = scenario_at(*key)
            if named != c.get("scenario"):
                out.append(f"{label}: scenario debe ser {named or 'ausente'}, no {c.get('scenario') or 'ausente'}")
            want_runs = 500 if named else 100
            if c["runs"] != want_runs:
                out.append(f"{label}: runs debe ser {want_runs}")
            try:
                raw = base64.b64decode(c["scores"], validate=True)
            except (binascii.Error, ValueError):
                out.append(f"{label}: scores no es base64 válido")
                continue
            want_bytes = len(STRATEGIES) * len(CRITERIA) * c["runs"]
            if len(raw) != want_bytes:
                out.append(f"{label}: scores mide {len(raw)} bytes y debe medir {want_bytes}")
            else:
                rows = len(STRATEGIES) * len(CRITERIA)
                for row in range(rows):
                    chunk = raw[row * c["runs"] : (row + 1) * c["runs"]]
                    if divmod(row, len(CRITERIA)) in declared:
                        if any(b != NO_DATA for b in chunk):
                            out.append(f"{label}: un criterio declarado en no_data debe valer {NO_DATA} en todas las corridas")
                            break
                    elif max(chunk) > 100:
                        out.append(f"{label}: hay puntajes mayores que 100")
                        break
        if len(seen) != 49:
            out.append(f"simulation.cells: faltan celdas de la grilla ({len(seen)} de 49)")
        if sim["strategies"] != list(STRATEGIES) or sim["criteria"] != list(CRITERIA):
            out.append("simulation: el orden de strategies o criteria no es el del contrato")
    return out


def package_problems(pkg: Any, nbytes: int | None = None) -> list[str]:
    """Esquema + comprobaciones + tamaño. Lista vacía = el paquete puede salir."""
    errors = schema_errors("parcel-package", pkg)
    if errors:
        return [f"esquema: {e}" for e in errors]
    out = semantic_problems(pkg)
    if nbytes is not None and nbytes >= MAX_PACKAGE_BYTES:
        out.append(f"pesa {nbytes / 1024:.1f} KB (límite 500 KB)")
    return out


def index_problems(index: Any) -> list[str]:
    return [f"esquema: {e}" for e in schema_errors("package-index", index)]


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted(p for p in PACKAGES_DIR.glob("*.json") if p.name != "index.json")
    failed = 0
    if not argv and (PACKAGES_DIR / "index.json").exists():
        problems = index_problems(json.loads((PACKAGES_DIR / "index.json").read_text(encoding="utf-8")))
        for p in problems:
            print(f"  FALLA index.json: {p}")
        failed += bool(problems)
    for path in paths:
        text = path.read_text(encoding="utf-8")
        problems = package_problems(json.loads(text), len(text.encode("utf-8")))
        if problems:
            failed += 1
            for p in problems:
                print(f"  FALLA {path.name}: {p}")
        else:
            print(f"  ok    {path.name}")
    print(f"\n{failed} archivo(s) con problemas." if failed else "\nTodo en regla.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
