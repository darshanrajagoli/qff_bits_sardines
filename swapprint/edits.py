"""Image edits shared by the app and the experiments (owner: Rashida).

Each edit is a pure function (img, **params) -> new canonical image (uint8, 256 x 256 x 3); the input is never
modified. `REGISTRY` maps each edit's name to its function, default parameters and category.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw

from . import synthetic
from .config import CANON


@dataclass(frozen=True)
class Edit:
    fn: Callable[..., np.ndarray]
    defaults: dict
    category: str  # "control", "imperceptible", "benign", "content" or "different"


def _check(img: np.ndarray) -> None:
    if not (isinstance(img, np.ndarray) and img.shape == (CANON, CANON, 3) and img.dtype == np.uint8):
        raise ValueError("edits need a canonical uint8 (256, 256, 3) image; use load_image() first")


def _check_box(y: int, x: int, size: int) -> None:
    if size < 1 or not (0 <= y and y + size <= CANON and 0 <= x and x + size <= CANON):
        raise ValueError(f"square at y={y}, x={x}, size={size} does not fit inside the {CANON}x{CANON} image")


def identity(img: np.ndarray) -> np.ndarray:
    """Unchanged copy (the control)."""
    _check(img)
    return img.copy()


def pixel(img: np.ndarray, y: int = 128, x: int = 128, channel: int = 0, delta: int = 1) -> np.ndarray:
    """Change one channel of one pixel by +delta (or by -delta if +delta would clip to no change)."""
    _check(img)
    _check_box(y, x, 1)
    if delta == 0:
        raise ValueError("delta must be non-zero")
    old = int(img[y, x, channel])
    new = min(max(old + delta, 0), 255)
    if new == old:
        new = min(max(old - delta, 0), 255)
    out = img.copy()
    out[y, x, channel] = new
    return out


def lsb(img: np.ndarray, payload: bytes | str = b"QFF", channel: int = 2) -> np.ndarray:
    """Hide `payload` in the least significant bits of one channel, MSB first, pixels row-major from (0, 0).

    If the payload's bits already match those LSBs, the first LSB is flipped so that the image always changes.
    """
    _check(img)
    data = payload.encode() if isinstance(payload, str) else bytes(payload)
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    if not 0 < bits.size <= CANON * CANON:
        raise ValueError(f"payload must hold 1 to {CANON * CANON // 8} bytes, got {len(data)}")
    ys, xs = np.divmod(np.arange(bits.size), CANON)
    old = img[ys, xs, channel]
    new = (old & 0xFE) | bits
    if np.array_equal(new, old):
        new[0] ^= 1
    out = img.copy()
    out[ys, xs, channel] = new
    return out


def jpeg(img: np.ndarray, quality: int = 90) -> np.ndarray:
    """Re-save as JPEG at `quality` and decode again (Pillow, in memory)."""
    _check(img)
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    with Image.open(buf) as im:
        return np.array(im.convert("RGB"), dtype=np.uint8)


def brightness(img: np.ndarray, delta: int = 2) -> np.ndarray:
    """Add `delta` to every channel value, clipped to [0, 255]."""
    _check(img)
    return np.clip(img.astype(np.int16) + delta, 0, 255).astype(np.uint8)


def contrast(img: np.ndarray, factor: float = 1.05) -> np.ndarray:
    """Scale every value's distance from 128 by `factor`, rounded (half to even) and clipped."""
    _check(img)
    return np.clip(np.rint((img.astype(np.float64) - 128) * factor + 128), 0, 255).astype(np.uint8)


def resize_roundtrip(img: np.ndarray, size: int = 128) -> np.ndarray:
    """Shrink to size x size and enlarge back to 256 x 256, both with Pillow's bilinear filter."""
    _check(img)
    small = Image.fromarray(img).resize((size, size), Image.Resampling.BILINEAR)
    return np.array(small.resize((CANON, CANON), Image.Resampling.BILINEAR), dtype=np.uint8)


def set_pixel(img: np.ndarray, y: int = 128, x: int = 128, rgb: tuple[int, int, int] = (255, 0, 0)) -> np.ndarray:
    """Set one pixel to the colour `rgb`."""
    _check(img)
    _check_box(y, x, 1)
    out = img.copy()
    out[y, x] = rgb
    return out


def patch(
    img: np.ndarray, y: int = 100, x: int = 100, size: int = 6, rgb: tuple[int, int, int] = (255, 0, 0)
) -> np.ndarray:
    """Paint a size x size square with top-left corner (y, x) in the colour `rgb`."""
    _check(img)
    _check_box(y, x, size)
    out = img.copy()
    out[y : y + size, x : x + size] = rgb
    return out


def copy_move(
    img: np.ndarray, src: tuple[int, int] = (20, 20), dst: tuple[int, int] = (150, 150), size: int = 24
) -> np.ndarray:
    """Copy the size x size square at `src` (y, x) of the original over the square at `dst`."""
    _check(img)
    (sy, sx), (dy, dx) = src, dst
    _check_box(sy, sx, size)
    _check_box(dy, dx, size)
    out = img.copy()
    out[dy : dy + size, dx : dx + size] = img[sy : sy + size, sx : sx + size]
    return out


def splice(img: np.ndarray, donor: np.ndarray, y: int = 64, x: int = 64, size: int = 48) -> np.ndarray:
    """Paste the size x size square at (y, x) of another canonical image `donor` into the same place."""
    _check(img)
    _check(donor)
    _check_box(y, x, size)
    out = img.copy()
    out[y : y + size, x : x + size] = donor[y : y + size, x : x + size]
    return out


def text(img: np.ndarray, s: str = "FAKE", y: int = 200, x: int = 10) -> np.ndarray:
    """Write `s` in white with Pillow's default font, top-left corner at (y, x)."""
    _check(img)
    im = Image.fromarray(img.copy())
    ImageDraw.Draw(im).text((x, y), s, fill=(255, 255, 255))
    return np.array(im, dtype=np.uint8)


def different(img: np.ndarray, other: np.ndarray | None = None) -> np.ndarray:
    """Replace the image by an unrelated artwork (the collision test): `other`, or a synthetic one by default."""
    _check(img)
    if other is None:
        other = _unrelated_artwork()
        if np.array_equal(other, img):
            other = synthetic.artwork(seed=2)
    _check(other)
    return other.copy()


@lru_cache(maxsize=1)
def _unrelated_artwork() -> np.ndarray:
    art = synthetic.artwork(seed=1)
    art.setflags(write=False)
    return art


def _splice_default_donor(img: np.ndarray, donor: np.ndarray | None = None, **params) -> np.ndarray:
    return splice(img, _unrelated_artwork() if donor is None else donor, **params)


REGISTRY: dict[str, Edit] = {
    "identity": Edit(identity, {}, "control"),
    "pixel": Edit(pixel, {"y": 128, "x": 128, "channel": 0, "delta": 1}, "imperceptible"),
    "lsb": Edit(lsb, {"payload": b"QFF", "channel": 2}, "imperceptible"),
    "jpeg": Edit(jpeg, {"quality": 90}, "benign"),
    "brightness": Edit(brightness, {"delta": 2}, "benign"),
    "contrast": Edit(contrast, {"factor": 1.05}, "benign"),
    "resize_roundtrip": Edit(resize_roundtrip, {"size": 128}, "benign"),
    "set_pixel": Edit(set_pixel, {"y": 128, "x": 128, "rgb": (255, 0, 0)}, "content"),
    "patch": Edit(patch, {"y": 100, "x": 100, "size": 6, "rgb": (255, 0, 0)}, "content"),
    "copy_move": Edit(copy_move, {"src": (20, 20), "dst": (150, 150), "size": 24}, "content"),
    "splice": Edit(_splice_default_donor, {"donor": None, "y": 64, "x": 64, "size": 48}, "content"),
    "text": Edit(text, {"s": "FAKE", "y": 200, "x": 10}, "content"),
    "different": Edit(different, {"other": None}, "different"),
}


def apply(img: np.ndarray, name: str, **overrides) -> np.ndarray:
    """Apply the registered edit `name` with its defaults, updated by `overrides`."""
    if name not in REGISTRY:
        raise ValueError(f"unknown edit {name!r}; choose from {sorted(REGISTRY)}")
    edit = REGISTRY[name]
    return edit.fn(img, **{**edit.defaults, **overrides})
