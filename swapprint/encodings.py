"""The three ways an image unit becomes the numbers that define its quantum state.

strict: a 4x4 tile's 384 bits -> 2048-bit codeword c, state (1/sqrt(2048)) sum_i (-1)^c_i |i> on 11 qubits.
perceptual: a 64x64 region's 64-bit DCT hash b, state (1/8) sum_i (-1)^b_i |i> on 6 qubits.
frqi (baseline): a 4x4 tile's 48 channel values and 16 zero angles on 6 + 1 qubits:
(1/8) sum_i (cos theta_i |0> + sin theta_i |1>) |i>, for i = 0..63.
Units are numbered row-major over the grid: unit = row * cols + col.
"""

from __future__ import annotations

import numpy as np

from .codes import encode
from .config import FRQI_POSITIONS, FRQI_VALUES, PERCEPTUAL_GRID, PERCEPTUAL_REGION, PERCEPTUAL_RULE, PHASH_AC_FLOOR, PHASH_FLAT_SIGMA, STRICT_GRID, STRICT_TILE


def tile_values(img: np.ndarray) -> np.ndarray:
    """(4096, 48) uint8: the channel values of each 4x4 tile; inside a tile, pixels row-major, then R, G, B."""
    g, t = STRICT_GRID, STRICT_TILE
    return img.reshape(g, t, g, t, 3).transpose(0, 2, 1, 3, 4).reshape(g * g, t * t * 3)


def strict(img: np.ndarray) -> np.ndarray:
    """(4096, 2048) uint8 0/1 codewords: each tile's 48 bytes unpacked to 384 bits (MSB first), then encoded."""
    return encode(np.unpackbits(tile_values(img), axis=1))


def perceptual(
    img: np.ndarray, *, rule: str | None = None, ac_floor: float | None = None, flat_sigma: float | None = None
) -> np.ndarray:
    """(16, 64) uint8 0/1 hash bits, one row per 64x64 region.

    Integer luminance Y = (299R + 587G + 114B + 500) // 1000 is averaged in 2x2 boxes to 32x32 float64.
    Take the top-left 8x8 of the orthonormal DCT-II, row-major. Bit 0 is fixed at zero.
    The default rule comes from PERCEPTUAL_RULE ("median"). The ablation "deadzone"
    sets each AC bit iff AC > ac_floor (default PHASH_AC_FLOOR).
    The "median" rule reproduces v0.2: AC > median(AC), with all bits zero when the
    AC RMS is below flat_sigma (default PHASH_FLAT_SIGMA). flat_sigma is used only
    by "median"; ac_floor only by "deadzone". Overrides are for ablations: compare
    these bits directly (overlap = 1 - 2 d / 64), not against registered fingerprints.
    """
    from scipy.fft import dctn  # imported lazily: scipy is slow to import

    rule = PERCEPTUAL_RULE if rule is None else rule
    if rule not in ("deadzone", "median"):
        raise ValueError(f"unknown perceptual rule {rule!r}; choose 'deadzone' or 'median'")
    rgb = img.astype(np.int64)
    y = (299 * rgb[..., 0] + 587 * rgb[..., 1] + 114 * rgb[..., 2] + 500) // 1000
    g, r = PERCEPTUAL_GRID, PERCEPTUAL_REGION
    regions = y.reshape(g, r, g, r).transpose(0, 2, 1, 3).reshape(g * g, r // 2, 2, r // 2, 2)
    regions = regions.mean(axis=(2, 4), dtype=np.float64)
    coeffs = dctn(regions, type=2, norm="ortho", axes=(1, 2))[:, :8, :8].reshape(g * g, 64)
    ac = coeffs[:, 1:]
    bits = np.zeros((g * g, 64), dtype=np.uint8)
    if rule == "deadzone":
        bits[:, 1:] = ac > (PHASH_AC_FLOOR if ac_floor is None else float(ac_floor))
    else:
        sigma = np.sqrt(np.mean(ac**2, axis=1))
        cutoff = PHASH_FLAT_SIGMA if flat_sigma is None else float(flat_sigma)
        bits[:, 1:] = (ac > np.median(ac, axis=1, keepdims=True)) & (sigma[:, None] >= cutoff)
    return bits


def frqi(img: np.ndarray) -> np.ndarray:
    """(4096, 64) float64 angles: theta = (pi/2) * v / 255 at positions 0..47, zero at 48..63.

    The standard FRQI state is (1/8) sum_i (cos theta_i |0> + sin theta_i |1>) |i>.
    Prepare it with Hadamards on six position qubits and uniformly controlled RY(2 theta_i) on the colour qubit.
    """
    angles = np.zeros((STRICT_GRID * STRICT_GRID, FRQI_POSITIONS), dtype=np.float64)
    angles[:, :FRQI_VALUES] = (np.pi / 2) * tile_values(img).astype(np.float64) / 255
    return angles
