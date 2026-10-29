"""The numbers behind the verdicts: SWAP-test statistics, the strict code's guarantee, and shot budgets.

A SWAP test on two states with overlap <a|b> reads 1 with probability p1 = (1 - overlap^2) / 2, so identical states
never read 1. If a changed tile has p1 >= p1_min, then k shots all read 0 (the change is missed) with probability at
most (1 - p1_min)^k.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from .config import CODE_SEED, STRICT_BITS, STRICT_M

NOTE = (
    "Holds with probability ≥ 1 − failure for a uniformly random generator matrix; ours is pseudo-random "
    "(SHAKE-256), so treat it as a heuristic guarantee."
)


def swap_test_p1(overlap: np.ndarray | float) -> np.ndarray:
    """Probability that the SWAP test's ancilla reads 1: (1 - overlap^2) / 2, clipped to [0, 0.5]."""
    return np.clip((1.0 - np.square(overlap)) / 2.0, 0.0, 0.5)


def code_info(failure: float = 1e-6) -> dict:
    """What the strict mode's [m=2048, n=384] code guarantees about any two different tiles.

    For a uniformly random linear code, the codeword of each fixed nonzero message has Binomial(m, 1/2) weight. A
    union bound over the 2^n - 1 nonzero messages and both tails (weight <= d makes the overlap close to +1, weight
    >= m - d makes it close to -1, and the SWAP test only sees overlap^2) gives: with probability >= 1 - failure,
    every nonzero codeword has weight in [d + 1, m - d - 1], where d is the largest integer with
    n ln 2 + ln 2 + ln P[Bin(m, 1/2) <= d] <= ln(failure). Then any changed tile has |overlap| <= overlap_max and
    p1 >= p1_min.
    """
    n, m = STRICT_BITS, STRICT_M
    d_min = _largest_bad_weight(float(failure)) + 1
    overlap_max = 1.0 - 2.0 * d_min / m
    return {
        "n": n,
        "m": m,
        "rate": n / m,
        "seed": CODE_SEED,
        "d_min_guaranteed": d_min,
        "overlap_max": overlap_max,
        "p1_min": (1.0 - overlap_max**2) / 2.0,
        "failure_prob": float(failure),
        "note": NOTE,
    }


@lru_cache(maxsize=None)
def _largest_bad_weight(failure: float) -> int:
    """Largest d with 2 * 2^n * P[Bin(m, 1/2) <= d] <= failure (union bound), or -1 if there is none."""
    if not 0.0 < failure < 1.0:
        raise ValueError(f"failure must be in (0, 1), got {failure}")
    n, m = STRICT_BITS, STRICT_M
    log_union = (n + 1) * math.log(2) + log_binom_half_cdf(m)[: m // 2 + 1]
    ok = np.flatnonzero(log_union <= math.log(failure))  # log_union increases with d, so `ok` is a prefix
    return int(ok[-1]) if ok.size else -1


def log_binom_half_cdf(m: int) -> np.ndarray:
    """ln P[Bin(m, 1/2) <= d] for d = 0..m.

    Same values as scipy.stats.binom.logcdf(d, m, 0.5) (checked in the tests), computed from log-gamma so that
    compare() never waits for scipy.stats, which takes 1.5 s or more to import.
    """
    log_pmf = [math.lgamma(m + 1) - math.lgamma(k + 1) - math.lgamma(m - k + 1) - m * math.log(2) for k in range(m + 1)]
    return np.logaddexp.accumulate(np.array(log_pmf))


def shots_needed(miss: float, p1: float) -> int:
    """Shots k such that a unit whose SWAP test reads 1 with probability p1 is missed with probability <= miss.

    All k shots read 0 with probability (1 - p1)^k, so k = ceil(ln(miss) / ln(1 - p1)).
    """
    if not 0.0 < p1 <= 0.5:
        raise ValueError(f"p1 must be in (0, 0.5], got {p1}")
    if not 0.0 < miss < 1.0:
        raise ValueError(f"miss must be in (0, 1), got {miss}")
    return math.ceil(math.log(miss) / math.log1p(-p1))
