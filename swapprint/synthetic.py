"""Deterministic synthetic "paintings", so tests and examples need no image files."""

from __future__ import annotations

import numpy as np

from .config import CANON


def artwork(seed: int = 0) -> np.ndarray:
    """A uint8 (256, 256, 3) synthetic painting: a four-colour gradient, filled circles and rectangles, mild grain.

    Only integer draws from numpy's seeded PCG64 generator and IEEE-exact arithmetic are used, so every machine
    produces the same pixels for the same seed.
    """
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:CANON, 0:CANON]
    wy = (y / (CANON - 1))[..., None]
    wx = (x / (CANON - 1))[..., None]
    tl, tr, bl, br = rng.integers(0, 256, size=(4, 3))
    img = tl * (1 - wy) * (1 - wx) + tr * (1 - wy) * wx + bl * wy * (1 - wx) + br * wy * wx

    for _ in range(int(rng.integers(3, 6))):
        cy, cx = rng.integers(0, CANON, size=2)
        r = int(rng.integers(12, 48))
        img[(y - cy) ** 2 + (x - cx) ** 2 < r * r] = rng.integers(0, 256, size=3)
    for _ in range(int(rng.integers(2, 5))):
        top, left = rng.integers(0, CANON - 16, size=2)
        h, w = rng.integers(16, 80, size=2)
        img[top : top + h, left : left + w] = rng.integers(0, 256, size=3)

    img += rng.integers(-6, 7, size=img.shape)
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)
