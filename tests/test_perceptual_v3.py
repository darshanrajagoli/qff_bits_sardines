"""Check that vectorizing E3 preserves its decision and selection semantics."""
import numpy as np
import pytest

from experiments.calibrate_perceptual import SHOTS_GRID, T_GRID, calc_image_flag_prob
from experiments.core_perceptual_v3 import FLOOR_GRID, probabilities, select


@pytest.mark.parametrize("shots", SHOTS_GRID)
@pytest.mark.parametrize("threshold", T_GRID)
def test_v3_exact_tails_match_e3(shots, threshold):
    # All attainable distances, including near-complements and exact equality.
    d = np.arange(65)[:, None]
    p1 = np.clip((1 - (1 - 2 * d / 64)**2) / 2, 0, .5)
    expected = [calc_image_flag_prob(p, shots, threshold) for p in p1]
    np.testing.assert_array_equal(probabilities(d, shots, threshold), expected)


def test_v3_selection_preserves_e3_stable_ties():
    # All candidates have identical content/benign rates. E3's remaining ties
    # resolve by floor/threshold loop order after the fewer-shots tie-break.
    d = np.zeros((len(FLOOR_GRID), 6, 14, 16), dtype=int)
    chosen, grid = select(d, list(range(6)), list(range(6, 14)))
    assert len(grid) == len(FLOOR_GRID) * len(SHOTS_GRID) * len(T_GRID)
    assert all(row["feasible"] for row in grid)
    assert (chosen["ac_floor"], chosen["shots"], chosen["threshold"]) == (5., 1024, .30)


def test_v3_selection_applies_limits_to_artwork_averages():
    # A single always-flagged benign case in one of six artworks has mean FA
    # 1/36 (>1%) and that artwork's average FA 1/6 (>5%): it is infeasible.
    d = np.zeros((len(FLOOR_GRID), 6, 14, 16), dtype=int)
    d[:, 0, 0, 0] = 32
    _, grid = select(d, list(range(6)), list(range(6, 14)))
    assert not any(row["feasible"] for row in grid)
    assert grid[0]["mean_benign"] == pytest.approx(1 / 36)
    assert grid[0]["max_benign"] == pytest.approx(1 / 6)
