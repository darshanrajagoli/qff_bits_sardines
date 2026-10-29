"""Statistical utilities for SwapPrint experiments and figures.

Includes:
- Wilson 95% confidence intervals for binomial proportions
- Non-parametric bootstrap confidence intervals across artworks
- Exact binomial and closed-form detection probabilities
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np
from scipy.stats import binom

from swapprint.config import PERCEPTUAL_F_THRESHOLD


def wilson_interval(successes: int | np.ndarray, n: int, confidence: float = 0.95) -> tuple[float | np.ndarray, float | np.ndarray]:
    """Calculate the Wilson score 95% (or specified) confidence interval for a binomial proportion.

    Returns (lower, upper). Handles 0/n and n/n bounds correctly without degenerate intervals.
    """
    if n <= 0:
        return 0.0, 1.0
    z = 1.959963984540054  # 95% two-sided normal quantile
    if confidence != 0.95:
        from scipy.stats import norm
        z = norm.ppf((1.0 + confidence) / 2.0)

    p_hat = successes / n
    denom = 1.0 + (z**2) / n
    center = (p_hat + (z**2) / (2.0 * n)) / denom
    margin = (z / denom) * np.sqrt((p_hat * (1.0 - p_hat)) / n + (z**2) / (4.0 * (n**2)))

    lower = np.maximum(0.0, center - margin)
    upper = np.minimum(1.0, center + margin)
    if isinstance(successes, (int, float, np.integer, np.floating)):
        return float(lower), float(upper)
    return lower, upper


def bootstrap_ci(
    values: np.ndarray | list[float],
    stat_fn: Callable[[np.ndarray], float] = np.mean,
    n_boot: int = 2000,
    confidence: float = 0.95,
    seed: int = 0,
) -> tuple[float, float, float]:
    """Calculate non-parametric bootstrap confidence interval for a statistic across items (e.g. artworks).

    Returns (point_estimate, lower_ci, upper_ci).
    """
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return 0.0, 0.0, 0.0
    if arr.size == 1:
        v = float(stat_fn(arr))
        return v, v, v

    point = float(stat_fn(arr))
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, arr.size, size=(n_boot, arr.size))
    boot_stats = np.array([stat_fn(arr[idx]) for idx in indices])

    alpha = 1.0 - confidence
    lower = float(np.percentile(boot_stats, 100.0 * (alpha / 2.0)))
    upper = float(np.percentile(boot_stats, 100.0 * (1.0 - alpha / 2.0)))
    return point, lower, upper


def exact_image_detection(
    p1: np.ndarray,
    shots: int,
    mode: str,
    threshold: float = PERCEPTUAL_F_THRESHOLD,
) -> float:
    """Calculate exact image detection probability (probability that at least one unit is flagged).

    - Strict / FRQI: 1 - prod_u (1 - p1_u)^shots, computed with log1p / expm1 for precision.
    - Perceptual: 1 - prod_u (1 - P_u(shots)), where P_u(shots) = P[Binomial(shots, p1_u) >= c_flag].
    """
    flat_p1 = np.asarray(p1, dtype=np.float64).ravel()
    if flat_p1.size == 0 or np.all(flat_p1 == 0.0):
        return 0.0

    if mode in ("strict", "frqi"):
        if np.any(flat_p1 >= 1.0):
            return 1.0
        sum_log1p = np.sum(np.log1p(-flat_p1))
        # 1 - exp(shots * sum_log1p)
        return float(-np.expm1(shots * sum_log1p))

    elif mode == "perceptual":
        counts = np.arange(shots + 1)
        flagged = np.flatnonzero(np.maximum(0.0, 1.0 - 2.0 * counts / shots) < threshold)
        if not flagged.size:
            return 0.0
        c_flag = int(flagged[0])
        p_u = binom.sf(c_flag - 1, shots, flat_p1)
        if np.any(p_u >= 1.0):
            return 1.0
        return float(-np.expm1(np.sum(np.log1p(-p_u))))

    raise ValueError(f"Unknown mode: {mode}")


def shots_99_image(
    p1: np.ndarray,
    mode: str,
    threshold: float = PERCEPTUAL_F_THRESHOLD,
    perceptual_grid: list[int] | None = None,
) -> int | str:
    """Smallest number of shots per unit to achieve image detection >= 0.99.

    - Strict / FRQI: exact closed form ceil(ln(0.01) / sum_u ln(1 - p1_u)).
    - Perceptual: smallest k in perceptual_grid where image detection >= 0.99, or '>16384'.
    - If all p1 are 0: returns 'never'.
    """
    flat_p1 = np.asarray(p1, dtype=np.float64).ravel()
    if flat_p1.size == 0 or np.all(flat_p1 == 0.0):
        return "never"

    if mode in ("strict", "frqi"):
        if np.any(flat_p1 >= 1.0):
            return 1
        sum_log1p = np.sum(np.log1p(-flat_p1))
        if sum_log1p == 0.0:
            return "never"
        target_log = math.log(0.01)
        k = math.ceil(target_log / sum_log1p)
        return max(1, k)

    elif mode == "perceptual":
        grid = perceptual_grid or [64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384]
        for k in grid:
            p_det = exact_image_detection(flat_p1, k, mode="perceptual", threshold=threshold)
            if p_det >= 0.99:
                return k
        return f">{grid[-1]}"

    raise ValueError(f"Unknown mode: {mode}")
