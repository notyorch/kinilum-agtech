"""Lo que el catálogo dice de ciclo, siembra, riegos y raíz es lo que dice la extracción de la Agenda Técnica de INIFAP."""

import csv

import pytest

from simulate.crops import RULES_DIR, crop_profile, load_catalog

MONTHS = {"enero": "ene", "febrero": "feb", "marzo": "mar", "octubre": "oct", "noviembre": "nov", "diciembre": "dic"}


def rows():
    with (RULES_DIR / "sources" / "inifap_agenda_sinaloa_2017.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def pick(crop, variable, like=None):
    out = [r for r in rows() if r["cultivo"] == crop and r["variable"] == variable and (like is None or like(r["detalle"]))]
    assert out, (crop, variable)
    return out


def numbers(rs):
    return [float(r["valor"]) for r in rs]


def date_of(text):
    day, month = text.split()
    return f"{int(day):02d}-{MONTHS[month]}"


def test_the_extraction_keeps_its_source_and_a_page_for_every_row():
    rs = rows()
    assert len(rs) == 248
    assert all(r["pagina_pdf"] and r["pagina_impresa"] for r in rs)
    # Todo dato (lo que el documento SÍ dice) trae además su tabla o sección; los «NO DICE» pueden no traerla.
    assert all(r["tabla_o_seccion"] for r in rs if r["valor"] != "NO DICE")


@pytest.mark.parametrize("crop,variant,start,end", [
    ("garbanzo", None, "15 noviembre", "15 diciembre"),
    ("trigo", None, "15 noviembre", "31 diciembre"),
    ("maiz", None, "25 octubre", "30 noviembre"),
    ("frijol", "azufrado", "1 octubre", "31 octubre"),
    ("frijol", "negro", "1 octubre", "31 octubre"),
])
def test_sowing_windows_are_the_ones_in_the_table(crop, variant, start, end):
    got = (load_catalog()["maiz_base"] if crop == "maiz" else crop_profile(crop, variant))["ventana_siembra"]
    assert got["inicio"] == date_of(start) and got["fin"] == date_of(end)
    assert "INIFAP" in got["fuente"]


def test_cycle_and_flowering_days_are_the_min_and_max_of_the_table():
    garb = numbers(pick("garbanzo", "dias_a_madurez"))
    assert (crop_profile("garbanzo")["ciclo_dias"]["min"], crop_profile("garbanzo")["ciclo_dias"]["max"]) == (min(garb), max(garb)) == (130, 140)
    trigo = numbers(pick("trigo", "dias_a_madurez"))
    assert (crop_profile("trigo")["ciclo_dias"]["min"], crop_profile("trigo")["ciclo_dias"]["max"]) == (min(trigo), max(trigo)) == (105, 120)
    azu = lambda d: any(k in d for k in ("Janasa", "Azufr"))
    neg = lambda d: "Negro" in d
    for variant, pred in (("azufrado", azu), ("negro", neg)):
        prof = crop_profile("frijol", variant)
        cyc, flo = numbers(pick("frijol", "ciclo_vegetativo", pred)), numbers(pick("frijol", "dias_a_floracion", pred))
        assert (prof["ciclo_dias"]["min"], prof["ciclo_dias"]["max"]) == (min(cyc), max(cyc)), variant
        assert (prof["dias_a_floracion"]["min"], prof["dias_a_floracion"]["max"]) == (min(flo), max(flo)), variant
    # Maíz: floración femenina, 84 a 106 días; es la regla que usa el pipeline.
    fem = numbers(pick("maiz", "dias_a_floracion_femenina"))
    base = load_catalog()["maiz_base"]["dias_a_floracion"]
    assert (base["min"], base["max"]) == (min(fem), max(fem)) == (84, 106)
    from harmonize.phenology import maize_rules

    assert maize_rules()["dias_a_floracion"] == [84, 106]


def test_irrigation_depths_add_up_to_the_totals_in_the_table():
    normal_net = sum(numbers(pick("maiz", f"riego_normal_{i}_lamina_neta")[0:1])[0] for i in range(1, 6))
    normal_gross = sum(numbers(pick("maiz", f"riego_normal_{i}_lamina_bruta")[0:1])[0] for i in range(1, 6))
    scarce_net = sum(numbers(pick("maiz", f"riego_escasez_{i}_lamina_neta")[0:1])[0] for i in range(1, 5))
    scarce_gross = sum(numbers(pick("maiz", f"riego_escasez_{i}_lamina_bruta")[0:1])[0] for i in range(1, 5))
    lam = load_catalog()["maiz_base"]["lamina_riego_mm"]
    assert (lam["neta_normal"], lam["bruta_normal"], lam["neta_escasez"], lam["bruta_escasez"]) == (normal_net, normal_gross, scarce_net, scarce_gross) == (446, 875, 420, 715)
    assert (lam["riegos_normal"], lam["riegos_escasez"]) == (5, 4)
    # Trigo: 15 cm de presiembra y tres auxilios de 10 cm = 45 cm = 450 mm.
    trigo = numbers(pick("trigo", "riego_3er_auxilio_lamina_acumulada"))[0]
    assert load_catalog()["cultivos"]["trigo"]["lamina_riego_mm"]["acumulada"] == trigo * 10 == 450


def test_root_depth_and_heat_threshold_come_from_the_table_and_what_it_does_not_say_stays_empty():
    assert max(numbers(pick("maiz", "profundidad_raiz"))) / 100 == load_catalog()["maiz_base"]["profundidad_raiz_m"] == 1.0
    assert crop_profile("sorgo")["umbral_calor_c"] == 40 and "40" in pick("sorgo", "temperatura_dano_floracion")[0]["valor"]
    for crop in ("frijol", "garbanzo", "sorgo", "trigo"):  # el documento no da lámina ni raíz de estos cultivos
        profile = crop_profile(crop, "azufrado") if crop == "frijol" else crop_profile(crop)
        assert profile["profundidad_raiz_m"] is None, crop
    for crop in ("frijol", "garbanzo", "sorgo"):
        assert (crop_profile(crop, "azufrado") if crop == "frijol" else crop_profile(crop))["lamina_riego_mm"] is None, crop
        assert pick(crop, "lamina_riego")[0]["valor"] == "NO DICE"
