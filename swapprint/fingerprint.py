"""Fingerprints: the classical description of one small quantum state per image unit.

The quantum states themselves are never stored; `data` holds what defines them (codewords, hash bits or angles), from
which overlaps are computed exactly and circuits can be built.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import BinaryIO, Callable, Union

import numpy as np

from . import encodings
from .config import (
    CANON,
    CODE_SEED,
    FRQI_Q,
    FRQI_POSITIONS,
    PERCEPTUAL_GRID,
    PERCEPTUAL_Q,
    PERCEPTUAL_REGION,
    PHASH_FLAT_SIGMA,
    STRICT_GRID,
    STRICT_Q,
    STRICT_TILE,
)

FORMAT = "swapprint-0.1"

# mode: (qubits per unit, grid, unit side in pixels, version string, encoder)
_MODES: dict[str, tuple[int, tuple[int, int], int, str, Callable[[np.ndarray], np.ndarray]]] = {
    "strict": (
        STRICT_Q,
        (STRICT_GRID, STRICT_GRID),
        STRICT_TILE,
        f"{FORMAT}/strict/q{STRICT_Q}/{CODE_SEED}",
        encodings.strict,
    ),
    "perceptual": (
        PERCEPTUAL_Q,
        (PERCEPTUAL_GRID, PERCEPTUAL_GRID),
        PERCEPTUAL_REGION,
        f"{FORMAT}/perceptual/q{PERCEPTUAL_Q}/r{PERCEPTUAL_REGION}/flat{PHASH_FLAT_SIGMA}",
        encodings.perceptual,
    ),
    "frqi": (FRQI_Q, (STRICT_GRID, STRICT_GRID), STRICT_TILE, f"{FORMAT}/frqi/q{FRQI_Q}/n{FRQI_POSITIONS}", encodings.frqi),
}
MODES = tuple(_MODES)


@dataclass(frozen=True)
class Fingerprint:
    """One quantum state per unit of a canonical image (see docs/CONTRACT.md).

    data: strict codewords (4096, 2048) uint8 0/1; perceptual hash bits (16, 64) uint8 0/1; frqi angles (4096, 64)
    float64. Row u describes unit u = row * cols + col.
    """

    mode: str
    q: int
    grid: tuple[int, int]
    unit_px: int
    data: np.ndarray
    version: str

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Fingerprint):
            return NotImplemented
        same_meta = (self.mode, self.q, self.grid, self.unit_px, self.version) == (
            other.mode,
            other.q,
            other.grid,
            other.unit_px,
            other.version,
        )
        return same_meta and self.data.dtype == other.data.dtype and np.array_equal(self.data, other.data)


def fingerprint(img: np.ndarray, mode: str = "strict") -> Fingerprint:
    """Fingerprint a canonical image (uint8, 256 x 256 x 3, from `load_image`) in mode "strict", "perceptual" or "frqi"."""
    if not (isinstance(img, np.ndarray) and img.shape == (CANON, CANON, 3) and img.dtype == np.uint8):
        got = f"{img.dtype} {img.shape}" if isinstance(img, np.ndarray) else type(img).__name__
        raise ValueError(f"fingerprint() needs a canonical uint8 (256, 256, 3) image, got {got}; use load_image() first")
    if mode not in _MODES:
        raise ValueError(f"unknown mode {mode!r}; choose from {MODES}")
    q, grid, unit_px, version, encode = _MODES[mode]
    data = encode(img)
    data.setflags(write=False)
    return Fingerprint(mode=mode, q=q, grid=grid, unit_px=unit_px, data=data, version=version)


def save_fingerprint(fp: Fingerprint, path: Union[str, "os.PathLike[str]", BinaryIO]) -> None:
    """Write `fp` to `path` (written exactly there, no extension added) as a compressed .npz.

    Strict codewords are stored bit-packed (8x smaller); everything is restored exactly by `load_fingerprint`.
    """
    packed = fp.mode == "strict"
    fields = dict(
        mode=fp.mode,
        q=fp.q,
        grid=np.asarray(fp.grid, dtype=np.int64),
        unit_px=fp.unit_px,
        version=fp.version,
        packed=packed,
        data_shape=np.asarray(fp.data.shape, dtype=np.int64),
        data=np.packbits(fp.data, axis=1) if packed else fp.data,
    )
    if isinstance(path, (str, os.PathLike)):
        with open(path, "wb") as f:
            np.savez_compressed(f, **fields)
    else:
        np.savez_compressed(path, **fields)


def load_fingerprint(path: Union[str, "os.PathLike[str]", BinaryIO]) -> Fingerprint:
    """Read a fingerprint written by `save_fingerprint`. Its data array is read-only."""
    with np.load(path, allow_pickle=False) as z:
        data = z["data"]
        if bool(z["packed"]):
            data = np.unpackbits(data, axis=1, count=int(z["data_shape"][1]))
        fp = Fingerprint(
            mode=str(z["mode"]),
            q=int(z["q"]),
            grid=tuple(int(v) for v in z["grid"]),
            unit_px=int(z["unit_px"]),
            data=data,
            version=str(z["version"]),
        )
    data.setflags(write=False)
    return fp
