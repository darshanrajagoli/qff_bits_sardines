"""The strict mode's error-correcting code: a pseudo-random linear [m=2048, n=384] binary code.

The generator matrix G (384 x 2048 bits) is expanded from the public seed with SHAKE-256, so everyone derives the same
code. A tile's 384 bits x become the codeword E(x) = xG mod 2. The code is linear, E(x) xor E(y) = E(x xor y), so the
overlap of two fingerprints depends only on which bits changed, and a random code spreads even a one-bit change over
about half of the 2048 code bits (overlap near 0).
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np

from .config import CODE_SEED, STRICT_BITS, STRICT_M
from .theory import code_info  # noqa: F401  (re-exported: the distance guarantee of this code)

SEED_PREFIX = b"swapprint/v0.1/strict-code/"


@lru_cache(maxsize=1)
def generator_matrix() -> np.ndarray:
    """The read-only (384, 2048) uint8 0/1 generator matrix: SHAKE-256 of the seed, unpacked most significant bit first."""
    stream = hashlib.shake_256(SEED_PREFIX + CODE_SEED.encode()).digest(STRICT_BITS * STRICT_M // 8)
    g = np.unpackbits(np.frombuffer(stream, dtype=np.uint8)).reshape(STRICT_BITS, STRICT_M)
    g.setflags(write=False)
    return g


@lru_cache(maxsize=1)
def _generator_f32() -> np.ndarray:
    g = generator_matrix().astype(np.float32)
    g.setflags(write=False)
    return g


def encode(bits: np.ndarray) -> np.ndarray:
    """Codewords E(x) = xG mod 2: messages (N, 384) uint8 0/1 -> codewords (N, 2048) uint8 0/1.

    The float32 matrix product is exact: every entry is an integer count of at most 384, far below 2^24. Its parity
    is then taken on integers, which gives the same bits as float `% 2` but is about 15x faster.
    """
    bits = np.asarray(bits)
    if bits.shape[-1] != STRICT_BITS:
        raise ValueError(f"messages must have {STRICT_BITS} bits in the last axis, got shape {bits.shape}")
    counts = bits.astype(np.float32) @ _generator_f32()
    return (counts.astype(np.uint16) & 1).astype(np.uint8)
