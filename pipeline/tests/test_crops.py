"""El catálogo de cultivos (pipeline/rules/) y lo que el simulador lee de él."""

import copy

import pytest

from simulate.crops import (
    PARAMS_BY_CRITERION,
    RULES_VERSION,
    criteria_without_data,
    crop_profile,
    fixes_nitrogen,
    load_catalog,
    rotation_block,
)
from simulate.scenarios import ROTATION_CROP, STRATEGIES


def test_catalog_has_exactly_the_four_rotation_crops():
    catalog = load_catalog()
    assert catalog["rules_version"] == RULES_VERSION
    assert set(catalog["cultivos"]) == {"frijol", "garbanzo", "sorgo", "trigo"}
    assert {c["estrategia"]: name for name, c in catalog["cultivos"].items()} == ROTATION_CROP
    assert {c["tipo"] for c in catalog["cultivos"].values()} == {"leguminosa", "cereal"}


def test_sorghum_and_wheat_get_no_nitrogen_bonus():
    assert not fixes_nitrogen("E3")
    assert not fixes_nitrogen("E5")
    assert not fixes_nitrogen("E0")
    assert fixes_nitrogen("E1") and fixes_nitrogen("E2") and fixes_nitrogen("E4")
    assert [s for s in STRATEGIES if fixes_nitrogen(s)] == ["E1", "E2", "E4"]


def test_a_crop_without_parameters_is_declared_no_data_and_does_not_fail():
    # Hoy todo el catálogo está «por definir»: agua, clima e ingreso salen sin dato, sin error.
    for crop in ("garbanzo", "trigo"):
        assert criteria_without_data(crop_profile(crop)) == ["water", "climate", "income"]
    # Suelo y erosión no dependen del perfil del cultivo: nunca faltan por él.
    assert "soil" not in PARAMS_BY_CRITERION and "erosion" not in PARAMS_BY_CRITERION
    assert criteria_without_data({}) == ["water", "climate", "income"]


def test_a_complete_profile_has_every_criterion():
    profile = copy.deepcopy(crop_profile("garbanzo"))
    profile.update(
        kc_por_etapa={"inicial": 0.4, "media": 1.0, "final": 0.35},
        profundidad_raiz_m=0.6,
        ciclo_dias=100,
        umbral_calor_c=35,
        ventana_siembra="octubre",
        rendimiento_t_ha={"min": 0.8, "max": 1.2},
        precio_mxn_t={"min": 1, "max": 2},
    )
    assert criteria_without_data(profile) == []
    # Con solo el precio sin definir, falta el ingreso y nada más.
    profile["precio_mxn_t"] = None
    assert criteria_without_data(profile) == ["income"]


def test_bean_variants_are_complete_profiles_and_negro_is_the_default_for_sinaloa():
    frijol = load_catalog()["cultivos"]["frijol"]
    assert set(frijol["variantes"]) == {"negro"}
    assert frijol["variante_por_defecto"] == "negro"
    assert crop_profile("frijol")["nombre"] == crop_profile("frijol", "negro")["nombre"] == "Frijol negro"
    for variant in frijol["variantes"]:
        profile = crop_profile("frijol", variant)
        for params in PARAMS_BY_CRITERION.values():
            assert all(p in profile for p in params), (variant, params)
        assert profile["fija_nitrogeno"] is True
        assert profile["estado_evidencia"] == "a_validar"
    with pytest.raises(ValueError):
        crop_profile("frijol", "espelon")


def test_every_rule_without_a_source_is_to_validate():
    catalog = load_catalog()
    assert catalog["method"] == "assumed"
    for rule in catalog["reglas"]:
        if rule["fuente"] is None:
            assert rule["estado_evidencia"] == "a_validar", rule["id"]
    for crop in catalog["cultivos"].values():
        assert crop["estado_evidencia"] == "a_validar"


def test_rotation_block_carries_only_the_chosen_variant():
    block = rotation_block("negro", "technician")
    assert block == {
        "rules_version": "crops.v2",
        "E2": {"rotation_crop": "frijol", "variant": "negro", "variant_chosen_by": "technician"},
        "E3": {"rotation_crop": "sorgo"},
        "E4": {"rotation_crop": "garbanzo"},
        "E5": {"rotation_crop": "trigo"},
    }
    with pytest.raises(ValueError):
        rotation_block("espelon")
