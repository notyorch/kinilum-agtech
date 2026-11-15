"""El armador de paquetes: del oro y la configuración al archivo publicado, sin tocar el repositorio."""

import copy
import json

import pytest

from package import build
from package.validate import package_problems

PARTS = ("values", "rain_this_season", "green_cover", "seasons", "thresholds", "normals", "map_30m")  # map_30m es opcional: solo si el paquete publicado lo trae


def gold_from(example: dict) -> dict:
    parts = {k: copy.deepcopy(example[k]) for k in PARTS if k in example}
    parts["_meta"] = {"clean_pixels": example["clean_pixels"]}
    return parts


def test_demo_config_is_valid():
    config = build.load_config("sin-demo-001")
    assert config["illustrative"] is True


def test_assemble_matches_the_published_example(example_package):
    config = build.load_config("sin-demo-001")
    pkg = build.assemble(config, gold_from(example_package), example_package["generated_at"])
    assert package_problems(pkg) == []
    assert pkg["restrictions"] == {k: example_package["restrictions"][k] for k in pkg["restrictions"]}
    assert pkg["area_ha"] == example_package["area_ha"]


def test_assemble_never_publishes_the_polygon(example_package):
    ring = [[-89.1234, 20.5678], [-89.1224, 20.5678], [-89.1224, 20.5688], [-89.1234, 20.5688], [-89.1234, 20.5678]]
    config = {**build.load_config("sin-demo-001"), "polygon": ring}
    pkg = build.assemble(config, gold_from(example_package), "2026-11-14")
    text = json.dumps(pkg)
    # Ni una sola coordenada del polígono exacto (el contorno del mapa va en metros locales, sin ubicación).
    assert not any(str(n) in text for point in ring for n in point)
    assert all(abs(n * 100 - round(n * 100)) < 1e-9 for n in pkg["reference_point"])
    assert 0.5 < pkg["area_ha"] < 2  # 0.0010° × 0.0010° ≈ 1 ha


def test_publish_names_the_file_and_updates_the_index(tmp_path, example_package):
    pkg = {**example_package, "generated_at": "2026-11-14"}
    name = build.publish(tmp_path, pkg, build.dumps(pkg))
    assert name == "sin-demo-001.2026-11-14.json"
    assert json.loads((tmp_path / "index.json").read_text())["parcels"]["sin-demo-001"]["file"] == name


def test_same_content_is_not_rewritten_and_changed_content_gets_a_revision(tmp_path, example_package):
    pkg = {**example_package, "generated_at": "2026-11-14"}
    first = build.publish(tmp_path, pkg, build.dumps(pkg))
    assert build.publish(tmp_path, pkg, build.dumps(pkg)) == first
    changed = {**pkg, "area_ha": 5}
    second = build.publish(tmp_path, changed, build.dumps(changed))
    assert second == "sin-demo-001.2026-11-14.r2.json"
    assert not (tmp_path / first).exists(), "el paquete anterior no debe quedar huérfano"


def test_changing_who_chose_the_bean_variant_changes_the_package_and_its_file_name(tmp_path, example_package):
    config = build.load_config("sin-demo-001")
    names = {}
    for chosen_by in ("team", "technician"):
        pkg = build.assemble({**config, "frijol_variante": "negro", "frijol_variante_elegida_por": chosen_by}, gold_from(example_package), "2026-11-14")
        assert package_problems(pkg) == []
        assert pkg["rotation"]["E2"] == {"rotation_crop": "frijol", "variant": "negro", "variant_chosen_by": chosen_by}
        names[chosen_by] = build.publish(tmp_path, pkg, build.dumps(pkg))
    assert names["team"] == "sin-demo-001.2026-11-14.json"
    assert names["technician"] == "sin-demo-001.2026-11-14.r2.json"  # contenido distinto el mismo día: otro nombre


def test_bean_variant_defaults_to_the_catalog_one(example_package):
    config = {k: v for k, v in build.load_config("sin-demo-001").items() if not k.startswith("frijol_variante")}
    pkg = build.assemble(config, gold_from(example_package), "2026-11-14")
    assert pkg["rotation"]["E2"] == {"rotation_crop": "frijol", "variant": "negro", "variant_chosen_by": "technician"}


def test_extreme_heat_is_derived_and_omitted_without_data(example_package):
    config = build.load_config("sin-demo-001")
    assert build.assemble(config, gold_from(example_package), "2026-11-14")["restrictions"]["extreme_heat"] is True
    gold = gold_from(example_package)
    gold["values"]["heat"].update(value=None, p10=None, p90=None)
    pkg = build.assemble(config, gold, "2026-11-14")
    assert "extreme_heat" not in pkg["restrictions"]
    assert package_problems(pkg) == []


def test_config_rejects_a_crop_outside_the_catalog():
    from common.schema import schema_errors

    config = build.load_config("sin-demo-001")
    assert schema_errors("parcel-config", {**config, "cultivos_aceptados": ["frijol", "arroz"]})
    assert schema_errors("parcel-config", {**config, "frijol_variante": "espelon"})


def test_build_refuses_missing_gold():
    with pytest.raises(build.BuildError):
        build.load_gold("no-existe")
