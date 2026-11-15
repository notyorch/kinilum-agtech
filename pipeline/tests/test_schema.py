"""El esquema acepta lo bueno y rechaza lo malo. Espejo de la autoprueba de app/scripts/check-schema.mjs."""

import base64
import copy
import json

import numpy as np

from package.validate import index_problems, package_problems
from simulate.encode import NO_DATA, cell_to_json
from simulate.scenarios import CRITERIA, STRATEGIES, cells

from common.schema import REPO

PACKAGES = REPO / "app" / "public" / "packages"


def synthetic_simulation() -> dict:
    """Bloque `simulation` con bytes pseudoaleatorios: solo prueba la FORMA, no es un resultado."""
    rng = np.random.default_rng(7)
    shape = (len(STRATEGIES), len(CRITERIA))
    return {
        "strategies": list(STRATEGIES),
        "criteria": list(CRITERIA),
        "rules_version": "crops.v2",
        "no_data": NO_INCOME,
        "cells": [cell_to_json(c, rng.integers(0, 101, size=(*shape, c.runs)), NO_INCOME) for c in cells()],
    }


# Garbanzo y trigo no tienen rendimiento ni precio con fuente: su ingreso va declarado sin dato.
NO_INCOME = {"E4": ["income"], "E5": ["income"]}


def test_example_package_passes(example_package):
    assert package_problems(example_package) == []


def test_index_passes():
    assert index_problems(json.loads((PACKAGES / "index.json").read_text(encoding="utf-8"))) == []


def test_simulation_with_six_strategies_passes_and_fits_the_budget(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["simulation"] = synthetic_simulation()
    assert pkg["simulation"]["strategies"] == ["E0", "E1", "E2", "E3", "E4", "E5"]
    text = json.dumps(pkg, separators=(",", ":"))
    assert package_problems(json.loads(text), len(text.encode())) == []
    assert len(text.encode()) < 500 * 1024


def test_undeclared_no_data_byte_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["simulation"] = synthetic_simulation()
    del pkg["simulation"]["no_data"]
    assert any("mayores que 100" in p for p in package_problems(pkg))


def test_declared_no_data_must_not_carry_scores(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["simulation"] = synthetic_simulation()
    pkg["simulation"]["no_data"]["E3"] = ["income"]
    assert any("no_data" in p for p in package_problems(pkg))


def test_strategy_with_another_crop_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["rotation"]["E4"] = {"rotation_crop": "trigo"}
    assert any("rotation.E4" in p for p in package_problems(pkg))


def test_crop_outside_the_catalog_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["restrictions"]["market"] = ["bean"]
    assert package_problems(pkg)


def test_example_package_names_the_bean_variant(example_package):
    assert example_package["rotation"]["E2"] == {"rotation_crop": "frijol", "variant": "azufrado", "variant_chosen_by": "team"}
    assert NO_DATA == 255


def test_missing_support_level_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    del pkg["values"]["rain"]["support_level"]
    assert package_problems(pkg)


def test_missing_range_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    del pkg["values"]["rain"]["p10"]
    assert package_problems(pkg)


def test_null_value_with_range_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["values"]["soil"]["p10"] = 20  # el suelo aluvial no tiene valor (sin dato): un rango sin valor se rechaza
    assert package_problems(pkg)


def test_unordered_range_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["values"]["rain"]["p10"] = 950
    assert any("p10 ≤ value" in p for p in package_problems(pkg))


def test_precise_reference_point_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["reference_point"] = [-89.62345, 20.97123]
    assert any("decimales" in p for p in package_problems(pkg))


def test_polygon_field_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["polygon"] = [[1, 2]]
    assert package_problems(pkg)


def test_score_over_100_is_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["simulation"] = synthetic_simulation()
    raw = bytearray(base64.b64decode(pkg["simulation"]["cells"][0]["scores"]))
    raw[0] = 101
    pkg["simulation"]["cells"][0]["scores"] = base64.b64encode(bytes(raw)).decode()
    assert any("mayores que 100" in p for p in package_problems(pkg))


def test_scores_of_the_wrong_length_are_rejected(example_package):
    pkg = copy.deepcopy(example_package)
    pkg["simulation"] = synthetic_simulation()
    pkg["simulation"]["cells"][1]["scores"] = base64.b64encode(bytes(10)).decode()
    assert any("bytes" in p for p in package_problems(pkg))
