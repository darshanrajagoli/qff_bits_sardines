"""Turn any image into the canonical 256x256 RGB uint8 array, bit-identically on every machine.

A fingerprint is only useful if the same file always gives the same bits, so resizing is integer-only box averaging
written in numpy (no Pillow resampling, no floating point).
"""

from __future__ import annotations

import io
import os
from typing import BinaryIO, Union

import numpy as np
from PIL import Image, ImageOps

from .config import CANON

ImageSource = Union[str, "os.PathLike[str]", bytes, bytearray, Image.Image, np.ndarray, BinaryIO]


def load_image(src: ImageSource) -> np.ndarray:
    """Return the canonical image of `src`: a C-contiguous uint8 array of shape (256, 256, 3).

    `src` may be a file path, the file's bytes (or an open binary file, such as a Streamlit upload), a PIL image, or
    an ndarray: H x W x 3 uint8, H x W x 4 (alpha is dropped) or H x W grey. Files and PIL images get their EXIF
    orientation applied and are converted to RGB. A 256 x 256 input comes back bit-identical.
    """
    if isinstance(src, np.ndarray):
        rgb = _rgb_from_array(src)
    elif isinstance(src, Image.Image):
        rgb = _rgb_from_pil(src)
    elif isinstance(src, (bytes, bytearray, memoryview)):
        with Image.open(io.BytesIO(src)) as im:
            rgb = _rgb_from_pil(im)
    elif isinstance(src, (str, os.PathLike)) or hasattr(src, "read"):
        with Image.open(src) as im:
            rgb = _rgb_from_pil(im)
    else:
        raise TypeError(f"cannot load an image from {type(src).__name__}; pass a path, bytes, PIL image or ndarray")
    return _box_resize(rgb)


def _rgb_from_pil(im: Image.Image) -> np.ndarray:
    return np.asarray(ImageOps.exif_transpose(im).convert("RGB"), dtype=np.uint8)


def _rgb_from_array(a: np.ndarray) -> np.ndarray:
    if a.dtype != np.uint8:
        raise ValueError(f"image arrays must be uint8, got {a.dtype}")
    if a.ndim == 2:
        return np.repeat(a[:, :, None], 3, axis=2)
    if a.ndim == 3 and a.shape[2] in (3, 4):
        return a[:, :, :3]
    raise ValueError(f"image arrays must be H x W, H x W x 3 or H x W x 4, got shape {a.shape}")


def _box_resize(rgb: np.ndarray) -> np.ndarray:
    """Resize an (H, W, 3) uint8 array to (256, 256, 3) with integer arithmetic only.

    Along an axis of length L, output index k covers source indices [b_k, b_k+1) with b_k = k*L // 256. If L >= 256
    each output value is the mean of its block; if L < 256 it is source index b_k (nearest neighbour). The axes are
    handled independently, sums are exact int64, and the mean is rounded half up once: (2s + c) // (2c).
    """
    sums, row_counts = _reduce_axis(rgb, axis=0)
    sums, col_counts = _reduce_axis(sums, axis=1)
    counts = (row_counts[:, None] * col_counts[None, :])[:, :, None]
    out = (sums.astype(np.int64) * 2 + counts) // (2 * counts)
    return np.ascontiguousarray(out, dtype=np.uint8)


def _reduce_axis(a: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
    """Block sums (or nearest-neighbour picks) of `a` along `axis`, and how many source pixels each output holds."""
    length = a.shape[axis]
    bounds = (np.arange(CANON + 1, dtype=np.int64) * length) // CANON
    if length >= CANON:  # every block is non-empty because length / 256 >= 1
        return np.add.reduceat(a, bounds[:-1], axis=axis, dtype=np.int64), np.diff(bounds)
    return np.take(a, bounds[:-1], axis=axis), np.ones(CANON, dtype=np.int64)
