"""Carga los esquemas de shared/schema/ y valida contra ellos.

El contrato es la interfaz entre el pipeline y la app: aquí se valida antes de escribir
(ARQUITECTURA-DEV §3). Las comprobaciones que el esquema JSON no expresa viven en
`package/validate.py` y repiten las de `app/scripts/check-schema.mjs`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

REPO = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO / "shared" / "schema"


def _read(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _registry() -> Registry:
    """Todos los esquemas, por su `$id`, para que los `$ref` entre archivos se resuelvan sin red."""
    registry: Registry = Registry()
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema, default_specification=DRAFT7))
    return registry


@lru_cache(maxsize=None)
def validator(name: str) -> Draft7Validator:
    """`validator("parcel-package")`, `validator("contract-value")`, `validator("parcel-config")`…"""
    return Draft7Validator(_read(f"{name}.schema.json"), registry=_registry())


def schema_errors(name: str, instance: Any, limit: int = 8) -> list[str]:
    """Lista de problemas (vacía = cumple el esquema), con la ruta de cada uno."""
    errors = sorted(validator(name).iter_errors(instance), key=lambda e: list(e.absolute_path))
    return [f"/{'/'.join(str(p) for p in e.absolute_path)} {e.message}"[:300] for e in errors[:limit]]
