"""El modelo del simulador: curva de Kc, necesidad de riego, ciclo por grados día y puntajes."""

import numpy as np
import pytest

from simulate import model

KC = {"inicial": 0.4, "media": 1.15, "final": 0.35}


def test_the_kc_curve_has_the_cycle_length_and_the_four_stages():
    c = model.kc_curve(100, [20, 30, 40, 10], KC)
    assert len(c) == 100
    assert c[0] == pytest.approx(0.4) and c[19] == pytest.approx(0.4)      # etapa inicial: constante
    assert c[34] == pytest.approx((0.4 + 1.15) / 2, abs=0.02)              # a mitad del desarrollo, entre los dos
    assert c[60] == pytest.approx(1.15) and c[89] == pytest.approx(1.15)   # etapa media: constante
    assert 0.35 < c[-1] < 0.4 and np.all(np.diff(c[90:]) <= 0)             # etapa final: baja a Kc final
    assert model.kc_curve(0, [1, 1, 1, 1], KC).size == 0


def test_stage_lengths_are_scaled_to_the_cycle_of_the_crop_not_the_fao_example():
    short, long = model.kc_curve(60, [25, 40, 45, 30], KC), model.kc_curve(180, [25, 40, 45, 30], KC)
    assert len(short) == 60 and len(long) == 180
    assert np.mean(long) == pytest.approx(np.mean(short), abs=0.02)  # mismas proporciones: mismo Kc medio


def test_irrigation_need_is_etc_minus_rain_and_never_negative():
    et0, rain = np.full(200, 4.0), np.zeros(200)
    r = model.crop_need(et0, rain, 10, 100, KC, [20, 30, 40, 10])
    assert r["etc"] == pytest.approx(float(np.sum(model.kc_curve(100, [20, 30, 40, 10], KC) * 4.0)))
    assert r["need"] == pytest.approx(r["etc"]) and r["days"] == 100 and r["cut"] is False
    wet = model.crop_need(et0, np.full(200, 50.0), 10, 100, KC, [20, 30, 40, 10])
    assert wet["need"] == 0.0 and wet["rain"] == 5000.0


def test_a_cycle_that_runs_past_the_series_is_cut_and_says_so():
    r = model.crop_need(np.full(50, 4.0), np.zeros(50), 30, 100, KC, [20, 30, 40, 10])
    assert r["days"] == 20 and r["cut"] is True


def test_the_maize_cycle_shortens_when_it_is_warmer():
    cool, warm = np.full(400, 16.0), np.full(400, 20.0)
    assert model.gdd_cycle_days(cool, 0, 1640.7) == 274 and model.gdd_cycle_days(warm, 0, 1640.7) == 165
    assert model.gdd_cycle_days(np.full(30, 20.0), 0, 1640.7) == 30  # si la serie no alcanza, los días que hay
    assert model.gdd_cycle_days(np.full(100, 40.0), 0, 1000) == 50   # el tope de 30 °C: 20 grados día por día


def test_sowing_windows_are_counted_from_the_first_of_october():
    assert [model.window_offset(d) for d in ("01-oct", "25-oct", "30-nov", "15-dic", "31-dic", "15-ene", "10-mar")] == [0, 24, 60, 75, 91, 106, 160]


def test_water_and_income_scores_are_0_to_100_and_move_the_right_way():
    need = np.array([0.0, 275.0, 550.0, 900.0])
    assert list(model.need_score(need, 550.0)) == [100.0, 50.0, 0.0, 0.0]
    rev = np.array([0.0, 42_000.0, 85_000.0, 120_000.0])
    assert list(model.income_score(rev, 85_000.0)) == pytest.approx([0.0, 42000 / 850, 100.0, 100.0])
