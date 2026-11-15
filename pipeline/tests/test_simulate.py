import numpy as np
import pytest

from simulate.encode import NO_DATA, cell_to_json, decode_scores, encode_scores
from simulate.scenarios import CRITERIA, NAMED, ROTATION_CROP, STRATEGIES, cells

SHAPE = (len(STRATEGIES), len(CRITERIA))


def test_six_strategies_share_the_same_49_cells():
    assert STRATEGIES == ("E0", "E1", "E2", "E3", "E4", "E5")
    assert ROTATION_CROP == {"E2": "frijol", "E3": "sorgo", "E4": "garbanzo", "E5": "trigo"}
    rng = np.random.default_rng(3)
    for strategy in ("E4", "E5"):
        i = STRATEGIES.index(strategy)
        produced = [decode_scores(cell_to_json(c, rng.integers(0, 101, size=(*SHAPE, c.runs)))["scores"], c.runs)[i] for c in cells()]
        assert len(produced) == 49
        assert all(block.shape == (len(CRITERIA), c.runs) for block, c in zip(produced, cells()))


def test_grid_has_49_distinct_cells_and_6_named_with_500_runs():
    grid = list(cells())
    assert len(grid) == 49
    assert len({(c.rain, c.temp) for c in grid}) == 49
    named = [c for c in grid if c.scenario]
    assert {c.scenario for c in named} == set(NAMED)
    assert all(c.runs == 500 for c in named)
    assert all(c.runs == 100 for c in grid if not c.scenario)


def test_encode_roundtrip():
    rng = np.random.default_rng(1)
    scores = rng.integers(0, 101, size=(*SHAPE, 100))
    assert np.array_equal(decode_scores(encode_scores(scores), 100), scores)


def test_a_criterion_without_data_is_declared_not_filled():
    scores = np.full((*SHAPE, 100), 50.0)
    income = CRITERIA.index("income")
    scores[STRATEGIES.index("E4"), income] = np.nan
    # Sin declararlo, un NaN no pasa…
    with pytest.raises(ValueError):
        encode_scores(scores)
    # …declarado, se escribe 255 y lo demás queda igual.
    decoded = decode_scores(encode_scores(scores, {"E4": ["income"]}), 100)
    assert np.all(decoded[STRATEGIES.index("E4"), income] == NO_DATA)
    assert np.all(np.delete(decoded.reshape(-1, 100), STRATEGIES.index("E4") * len(CRITERIA) + income, axis=0) == 50)


@pytest.mark.parametrize(
    "bad",
    [np.full((*SHAPE, 3), 101), np.full((*SHAPE, 3), -1), np.full((*SHAPE, 3), np.nan), np.zeros((4, 5, 3))],
)
def test_encode_rejects_invalid_scores(bad):
    with pytest.raises(ValueError):
        encode_scores(bad)


def test_cell_to_json_checks_the_run_count():
    first_named = next(c for c in cells() if c.scenario)
    with pytest.raises(ValueError):
        cell_to_json(first_named, np.zeros((*SHAPE, 100)))
