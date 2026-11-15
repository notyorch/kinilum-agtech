"""El simulador de punta a punta con un clima sintético: forma del bloque, corridas compartidas y lo declarado sin dato."""

import numpy as np
import pytest

from simulate import run
from simulate.encode import NO_DATA, decode_scores
from simulate.scenarios import CRITERIA, STRATEGIES, cells


def fake_seasons(n=3, seed=1):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        dates = np.arange(np.datetime64(f"{2016 + i}-10-01"), np.datetime64(f"{2017 + i}-09-30") + np.timedelta64(1, "D"))
        doy = (dates - dates.astype("datetime64[Y]")).astype(int)
        t = 24 + 7 * np.sin((doy - 100) / 365 * 2 * np.pi) + rng.normal(0, 0.5, len(dates))
        out.append({"dates": dates, "t": t, "tmax": t + 6, "tmin": t - 6, "rh": np.full(len(dates), 60.0), "rs": np.full(len(dates), 18.0), "rain": np.where(rng.random(len(dates)) < 0.05, rng.gamma(2, 6, len(dates)), 0.0)})
    return out


@pytest.fixture(scope="module")
def result():
    specs = run.crop_specs("azufrado")
    table = {"anios": list(range(2015, 2025)), "cultivos": {c: {"rendimiento_t_ha": [r] * 10, "pmr_mxn_t": [p] * 10} for c, (r, p) in {"maiz": (12.0, 5000.0), "frijol": (2.0, 22000.0), "garbanzo": (2.2, 17000.0), "sorgo": (6.0, 5000.0), "trigo": (6.0, 5800.0)}.items()}}
    return run.simulate(fake_seasons(), 25.5, 15.0, specs, run.siap_revenue(table)), specs


def test_there_are_49_cells_with_500_or_100_runs_and_the_right_byte_length(result):
    res, _ = result
    assert len(res["cells"]) == 49
    for cell, js in zip(cells(), res["cells"]):
        assert (js["rain"], js["temp"], js["runs"]) == (cell.rain, cell.temp, cell.runs)
        assert decode_scores(js["scores"], js["runs"]).shape == (6, 5, cell.runs)
    assert sum(1 for c in res["cells"] if "scenario" in c) == 6


def test_what_has_no_data_is_declared_255_and_what_has_data_is_0_to_100(result):
    res, _ = result
    s = decode_scores(res["cells"][0]["scores"], res["cells"][0]["runs"])
    water, income = CRITERIA.index("water"), CRITERIA.index("income")
    for i, st in enumerate(STRATEGIES):
        for c in ("soil", "erosion", "climate"):
            assert (s[i, CRITERIA.index(c)] == NO_DATA).all(), (st, c)
    assert (s[STRATEGIES.index("E1")] == NO_DATA).all()  # sin datos de agua ni de costo de la cobertura
    for st in ("E0", "E2", "E3", "E4", "E5"):
        for c in (water, income):
            assert ((s[STRATEGIES.index(st), c] >= 0) & (s[STRATEGIES.index(st), c] <= 100)).all(), (st, c)


def test_more_rain_means_less_irrigation_and_the_runs_are_the_same_years_for_every_strategy(result):
    res, _ = result
    raw = {(r["cell"].rain, r["cell"].temp): r for r in res["raw"]}
    dry, wet = raw[(-30, 0)]["need"][0].mean(), raw[(30, 0)]["need"][0].mean()
    assert dry >= wet  # con lluvia tan escasa casi no cambia, pero nunca baja
    r = raw[(0, 0)]
    # La misma corrida es el mismo año: la necesidad de E0 y de E2 se mueven juntas, porque ambas llevan el maíz de ese año.
    assert np.corrcoef(r["need"][0], r["need"][2])[0, 1] > 0.5


def test_the_same_seed_gives_the_same_scores():
    specs = run.crop_specs("azufrado")
    table = {"anios": list(range(2015, 2025)), "cultivos": {c: {"rendimiento_t_ha": [1.0] * 10, "pmr_mxn_t": [1000.0] * 10} for c in ("maiz", "frijol", "garbanzo", "sorgo", "trigo")}}
    a = run.simulate(fake_seasons(2), 25.5, 15.0, specs, run.siap_revenue(table))
    b = run.simulate(fake_seasons(2), 25.5, 15.0, specs, run.siap_revenue(table))
    assert [c["scores"] for c in a["cells"]] == [c["scores"] for c in b["cells"]]


def test_a_season_with_a_missing_day_is_left_out_of_the_simulation():
    s = fake_seasons(1)[0]
    from ingest.contract import Series

    dates = s["dates"]
    power = Series(dates, {"T2M": s["t"], "T2M_MAX": s["tmax"], "T2M_MIN": s["tmin"], "RH2M": s["rh"], "ALLSKY_SFC_SW_DWN": s["rs"]})
    imerg = Series(dates, {"precip_mm_day": s["rain"].copy()})
    assert run.season_arrays(power, imerg, 2016) is not None
    imerg.columns["precip_mm_day"][10] = np.nan
    assert run.season_arrays(power, imerg, 2016) is None


def test_the_crop_specs_come_from_the_catalog_with_the_chosen_bean():
    specs = run.crop_specs("negro")
    assert specs["frijol"]["cycle"] == 120 and specs["maiz"]["cycle"] is None  # el ciclo del maíz sale de los grados día
    assert run.crop_specs("azufrado")["frijol"]["cycle"] == 100
    assert specs["trigo"]["cycle"] == 113 and specs["garbanzo"]["cycle"] == 135 and specs["sorgo"]["cycle"] == 135


def test_every_cell_carries_the_water_each_strategy_asks_for_in_mm(result):
    res, _ = result
    for js in res["cells"]:
        w = js["water_mm"]
        assert sorted(w) == ["E0", "E2", "E3", "E4", "E5"]  # E1 no aparece: no tiene dato
        for p10, p50, p90 in w.values():
            assert 0 <= p10 <= p50 <= p90
    # Es el mismo dato que el puntaje de agua: la estrategia que pide menos tiene el mejor puntaje.
    js = res["cells"][0]
    scores = decode_scores(js["scores"], js["runs"])
    water = CRITERIA.index("water")
    by_need = sorted(js["water_mm"], key=lambda st: js["water_mm"][st][1])
    by_score = sorted(js["water_mm"], key=lambda st: -float(np.median(scores[STRATEGIES.index(st), water])))
    assert by_need == by_score
