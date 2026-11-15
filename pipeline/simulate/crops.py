"""Lee el catálogo de cultivos (pipeline/rules/crops.<versión>.yaml) para el simulador y el armador.

El catálogo dice qué cultivo trae cada estrategia, cuáles suman nitrógeno y qué parámetros faltan.
Un parámetro que falta (`null` = por definir) NO se inventa: el criterio que lo necesita se declara
«sin dato» y los demás se calculan sin él (degradación elegante).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from common.schema import REPO

from .scenarios import ROTATION_CROP

RULES_DIR = REPO / "pipeline" / "rules"
RULES_VERSION = "crops.v2"

# Qué parámetros del perfil necesita cada criterio. Erosión y suelo no dependen del perfil del
# cultivo de rotación (salen de la cubierta, la pendiente y la lluvia), así que nunca faltan por él.
PARAMS_BY_CRITERION: dict[str, tuple[str, ...]] = {
    # El modelo de agua v1 es ETc − lluvia por ciclo (sin reserva de agua en el suelo): no usa la profundidad de raíz.
    "water": ("kc_por_etapa", "ciclo_dias", "ventana_siembra"),
    "climate": ("umbral_calor_c", "ventana_siembra"),
    "income": ("rendimiento_t_ha", "precio_mxn_t"),
}


@lru_cache(maxsize=None)
def load_catalog(version: str = RULES_VERSION) -> dict[str, Any]:
    path = RULES_DIR / f"{version}.yaml"
    catalog = yaml.safe_load(path.read_text(encoding="utf-8"))
    if catalog["rules_version"] != version:
        raise ValueError(f"{path.name}: rules_version dice {catalog['rules_version']}, no {version}")
    return catalog


def crop_profile(crop: str, variant: str | None = None, version: str = RULES_VERSION) -> dict[str, Any]:
    """El perfil con el que se simula un cultivo. Para el frijol, el de la variante elegida."""
    base = load_catalog(version)["cultivos"][crop]
    variants = base.get("variantes")
    if not variants:
        return base
    chosen = variant or base["variante_por_defecto"]
    if chosen not in variants:
        raise ValueError(f"{crop}: la variante {chosen} no está en el catálogo ({', '.join(variants)})")
    # La variante es un perfil completo; del cultivo solo hereda lo que no depende de la variante.
    shared = {k: v for k, v in base.items() if k not in ("variantes", "variante_por_defecto", "ciclo_dias")}
    return {**shared, **variants[chosen]}


def _missing(value: Any) -> bool:
    """`null` es «por definir»; un bloque al que le falta CUALQUIER campo, también (un Kc sin la etapa inicial no sirve)."""
    if isinstance(value, dict):
        return any(_missing(v) for v in value.values())
    return value is None


def criteria_without_data(profile: dict[str, Any]) -> list[str]:
    """Criterios que no se pueden calcular con este perfil. Nunca falla: lo que falta se declara."""
    return [c for c, params in PARAMS_BY_CRITERION.items() if any(_missing(profile.get(p)) for p in params)]


def fixes_nitrogen(strategy: str, version: str = RULES_VERSION) -> bool:
    """Solo las leguminosas suman nitrógeno: la cobertura de E1, el frijol y el garbanzo. Sorgo y trigo, no."""
    if strategy == "E1":
        return True
    crop = ROTATION_CROP.get(strategy)
    return bool(crop) and load_catalog(version)["cultivos"][crop]["fija_nitrogeno"] is True


def rotation_block(variant: str | None, chosen_by: str = "technician", version: str = RULES_VERSION) -> dict[str, Any]:
    """El bloque `rotation` del paquete: cultivo por estrategia y, en E2, la variante de frijol simulada."""
    catalog = load_catalog(version)
    block: dict[str, Any] = {"rules_version": catalog["rules_version"]}
    for strategy, crop in ROTATION_CROP.items():
        if catalog["cultivos"][crop]["estrategia"] != strategy:
            raise ValueError(f"el catálogo pone {crop} en {catalog['cultivos'][crop]['estrategia']}, no en {strategy}")
        block[strategy] = {"rotation_crop": crop}
    frijol = catalog["cultivos"]["frijol"]
    chosen = variant or frijol["variante_por_defecto"]
    if chosen not in frijol["variantes"]:
        raise ValueError(f"frijol_variante: {chosen} no está en el catálogo")
    block["E2"] = {"rotation_crop": "frijol", "variant": chosen, "variant_chosen_by": chosen_by}
    return block
