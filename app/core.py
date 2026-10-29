"""Pure helpers for the SwapPrint app: no Streamlit here, so the demo tests can import them.

Everything goes through swapprint's public API (docs/CONTRACT.md).
"""

from __future__ import annotations

import hashlib
import io
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import swapprint as sp  # noqa: E402

ART_DIR = ROOT / "data" / "artworks"
FIG_DIR = ROOT / "experiments" / "figures"

MODES = ("strict", "perceptual", "frqi")
MODE_LABEL = {"strict": "strict", "perceptual": "perceptual", "frqi": "frqi (baseline)"}
UNIT_WORD = {"strict": "tile", "perceptual": "region", "frqi": "tile"}

ACCENT = (232, 65, 214)  # magenta: the one accent colour, colour-blind safe against the greys
GAME_HIT_PX = 8  # a spot-the-edit guess within 8 canonical pixels counts as a hit
MAX_UPLOAD_PIXELS = 40_000_000


# ---------------------------------------------------------------- artworks


@dataclass(frozen=True)
class Artwork:
    file: str
    title: str
    artist: str
    year: str


def gallery() -> list[Artwork]:
    """Artworks in data/artworks/ with titles from SOURCES.md (file name as title if a row is missing)."""
    rows: dict[str, Artwork] = {}
    sources = ART_DIR / "SOURCES.md"
    if sources.exists():
        for line in sources.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\|\s*`([^`]+\.png)`\s*\|([^|]*)\|([^|]*)\|([^|]*)\|", line)
            if m:
                file, title, artist, year = (s.strip() for s in m.groups())
                title = re.split(r"\s+\(|,\s+from the series", title)[0]  # drop long Japanese subtitles
                artist = re.sub(r"\s*\(.*\)", "", artist)
                rows[file] = Artwork(file, title, artist, year)
    out = []
    for path in sorted(ART_DIR.glob("*.png")):
        out.append(rows.get(path.name, Artwork(path.name, path.stem.replace("_", " ").title(), "", "")))
    # paintings first, the generated stress tests last
    return sorted(out, key=lambda a: (a.artist == "team sardines", a.file))


def load_artwork(file: str) -> np.ndarray:
    return sp.load_image(ART_DIR / file)


def load_upload(data: bytes) -> tuple[np.ndarray, list[str]]:
    """Canonical image from uploaded bytes, plus notes on what was done to it. Raises ValueError with a friendly message."""
    notes: list[str] = []
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.width * im.height > MAX_UPLOAD_PIXELS:
                raise ValueError(f"that image is {im.width}×{im.height}; please upload one under 40 megapixels")
            im = ImageOps.exif_transpose(im)
            if im.mode in ("I;16", "I;16B", "I;16L", "I;16N", "I"):
                a = np.asarray(im, dtype=np.float64)
                hi = a.max() if a.max() > 255 else 255.0
                im = Image.fromarray(np.clip(a * 255.0 / hi, 0, 255).astype(np.uint8), "L")
                notes.append("converted 16-bit greyscale to 8 bits")
            elif im.mode == "F":
                a = np.asarray(im, dtype=np.float64)
                im = Image.fromarray(np.clip(a * (255.0 if a.max() <= 1 else 1.0), 0, 255).astype(np.uint8), "L")
                notes.append("converted floating-point greyscale to 8 bits")
            if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
                notes.append("transparency dropped")
            if im.mode == "CMYK":
                notes.append("converted CMYK to RGB")
            im = im.convert("RGB")
            if im.width != im.height:
                s = min(im.width, im.height)
                left, top = (im.width - s) // 2, (im.height - s) // 2
                im = im.crop((left, top, left + s, top + s))
                notes.append(f"centre-cropped to a {s}×{s} square")
            if im.size != (sp.config.CANON, sp.config.CANON):
                notes.append(f"resized to the canonical {sp.config.CANON}×{sp.config.CANON}")
            return sp.load_image(im), notes
    except ValueError:
        raise
    except Exception as exc:  # PIL raises many types for corrupt or exotic files
        raise ValueError("that file could not be read as an image; try a PNG or JPEG") from exc


def sha(img: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(img).tobytes()).hexdigest()


def to_png(img: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(img).save(buf, format="PNG")
    return buf.getvalue()


def upscale(img: np.ndarray, size: int = 512) -> Image.Image:
    return Image.fromarray(img).resize((size, size), Image.NEAREST)


# ---------------------------------------------------------------- edits

# name -> (label, needs a location)
TOOLS = {
    "pixel": ("Nudge one pixel by ±1 (invisible)", True),
    "set_pixel": ("Recolour one pixel", True),
    "patch": ("Paint a square patch", True),
    "text": ("Write text", True),
    "copy_move": ("Copy a square elsewhere (copy-move)", True),
    "splice": ("Splice in a square from another artwork", True),
    "lsb": ("Hide a message in the lowest bits (LSB)", False),
    "brightness": ("Brightness", False),
    "contrast": ("Contrast", False),
    "jpeg": ("Re-save as JPEG", False),
    "resize_roundtrip": ("Shrink and enlarge again", False),
}


def clamp_box(y: int, x: int, size: int) -> tuple[int, int]:
    """Top-left corner that keeps a size×size square inside the canonical image."""
    hi = sp.config.CANON - size
    return min(max(int(y), 0), hi), min(max(int(x), 0), hi)


def apply_step(img: np.ndarray, step: dict) -> np.ndarray:
    """Apply one history step {"name", "params"}; a splice donor is stored as a gallery file name."""
    params = dict(step["params"])
    if step["name"] == "splice":
        params["donor"] = load_artwork(params.pop("donor_file"))
    if step["name"] == "lsb" and isinstance(params.get("payload"), str):
        params["payload"] = params["payload"].encode("utf-8")
    for key in ("rgb", "src", "dst"):
        if key in params:
            params[key] = tuple(params[key])
    return sp.edits.apply(img, step["name"], **params)


def replay(base: np.ndarray, history: list[dict]) -> np.ndarray:
    img = base
    for step in history:
        img = apply_step(img, step)
    return img


def surprise(seed: int, n: int) -> dict:
    """A random imperceptible edit (one channel of one pixel ±1) at a spot drawn from (seed, n): repeatable."""
    rng = np.random.default_rng([int(seed), int(n)])
    y, x = (int(v) for v in rng.integers(16, sp.config.CANON - 16, size=2))
    return {"name": "pixel", "params": {"y": y, "x": x, "channel": int(rng.integers(3)), "delta": int(rng.choice([-1, 1]))}}


def describe(step: dict) -> str:
    p = step["params"]
    n = step["name"]
    if n == "pixel":
        return f"pixel ({p['y']}, {p['x']}), {'RGB'[p['channel']]} channel {p['delta']:+d}"
    if n == "set_pixel":
        return f"recolour pixel ({p['y']}, {p['x']}) to rgb{tuple(p['rgb'])}"
    if n == "patch":
        return f"{p['size']}×{p['size']} patch at ({p['y']}, {p['x']}), rgb{tuple(p['rgb'])}"
    if n == "text":
        return f"text “{p['s']}” at ({p['y']}, {p['x']})"
    if n == "copy_move":
        return f"copy {p['size']}×{p['size']} from {tuple(p['src'])} to {tuple(p['dst'])}"
    if n == "splice":
        return f"splice {p['size']}×{p['size']} at ({p['y']}, {p['x']}) from {p['donor_file']}"
    if n == "lsb":
        return f"hide “{p['payload']}” in the lowest bits"
    if n == "brightness":
        return f"brightness {p['delta']:+d}"
    if n == "contrast":
        return f"contrast ×{p['factor']}"
    if n == "jpeg":
        return f"JPEG re-save, quality {p['quality']}"
    if n == "resize_roundtrip":
        return f"shrink to {p['size']}×{p['size']} and back"
    return n


# ---------------------------------------------------------------- fingerprint visuals


def mosaic(fp: sp.Fingerprint) -> np.ndarray:
    """One colour per unit from the first 24 bits of its codeword/hash (or FRQI angles): looks like noise on purpose."""
    if fp.mode == "frqi":
        vals = np.round(fp.data[:, :3] / (np.pi / 2) * 255).astype(np.uint8)
    else:
        bits = np.asarray(fp.data[:, :24], dtype=np.uint8)
        vals = np.packbits(bits, axis=1)  # 24 bits -> 3 bytes
    return vals.reshape(*fp.grid, 3)


def mosaic_image(fp: sp.Fingerprint, size: int = 512, changed: np.ndarray | None = None) -> Image.Image:
    im = Image.fromarray(mosaic(fp)).resize((size, size), Image.NEAREST)
    if changed is not None:
        _rings(im, changed, fp.grid, (255, 255, 255))
    return im


def _rings(im: Image.Image, mask: np.ndarray, grid: tuple[int, int], colour, width: int = 2, limit: int = 60) -> None:
    rows, cols = grid
    cell = im.width / cols
    idx = np.argwhere(mask)
    if len(idx) == 0 or len(idx) > limit:
        return
    d = ImageDraw.Draw(im)
    pad = max(4, cell * 0.8)
    for r, c in idx:
        x0, y0 = c * cell - pad, r * cell - pad
        d.ellipse([x0, y0, x0 + cell + 2 * pad, y0 + cell + 2 * pad], outline=colour, width=width)


def heatmap(img: np.ndarray, cmp: sp.Comparison, size: int = 512, guess=None, truth=None) -> Image.Image:
    """Flagged units tinted magenta with opacity from p1, ringed when few, on a slightly dimmed copy of the image."""
    base = upscale(img, size).convert("RGBA")
    base = Image.blend(base, Image.new("RGBA", base.size, (20, 20, 24, 255)), 0.35)
    rows, cols = cmp.grid
    alpha = np.where(cmp.flagged, 0.35 + 0.65 * np.clip(cmp.p1 / 0.5, 0, 1), 0.0)
    a = Image.fromarray((alpha * 230).astype(np.uint8), "L").resize((size, size), Image.NEAREST)
    tint = Image.new("RGBA", base.size, ACCENT + (255,))
    tint.putalpha(a)
    out = Image.alpha_composite(base, tint).convert("RGB")
    _rings(out, cmp.flagged, cmp.grid, ACCENT + (), width=3)
    d = ImageDraw.Draw(out)
    scale = size / sp.config.CANON
    if truth is not None:
        ty, tx = truth
        cx, cy = (tx + 0.5) * scale, (ty + 0.5) * scale
        d.rectangle([cx - 10, cy - 10, cx + 10, cy + 10], outline=(255, 255, 255), width=2)
    if guess is not None:
        gy, gx = guess
        cx, cy = (gx + 0.5) * scale, (gy + 0.5) * scale
        d.line([cx - 12, cy, cx + 12, cy], fill=(255, 210, 0), width=3)
        d.line([cx, cy - 12, cx, cy + 12], fill=(255, 210, 0), width=3)
    return out


def most_suspicious(cmp: sp.Comparison) -> int:
    """Unit with the largest p1 (ties: lowest index), the one the live trace and Aer default to."""
    return int(np.argmax(cmp.p1.reshape(-1)))


def unit_rc(cmp_or_grid, unit: int) -> tuple[int, int]:
    grid = cmp_or_grid.grid if hasattr(cmp_or_grid, "grid") else cmp_or_grid
    return divmod(int(unit), grid[1])


def zoom_pair(a: np.ndarray, b: np.ndarray, unit: int, grid, unit_px: int, size: int = 240) -> tuple[Image.Image, Image.Image]:
    """The unit with one unit of context on each side, from both images, enlarged with crisp pixels and ringed."""
    r, c = unit_rc(grid, unit)
    ctx = unit_px if unit_px < 64 else 0
    y0, x0 = max(0, r * unit_px - ctx), max(0, c * unit_px - ctx)
    y1, x1 = min(sp.config.CANON, (r + 1) * unit_px + ctx), min(sp.config.CANON, (c + 1) * unit_px + ctx)
    out = []
    for img in (a, b):
        crop = Image.fromarray(img[y0:y1, x0:x1]).resize((size, size * (y1 - y0) // (x1 - x0)), Image.NEAREST)
        s = size / (x1 - x0)
        ImageDraw.Draw(crop).rectangle(
            [(c * unit_px - x0) * s, (r * unit_px - y0) * s, ((c + 1) * unit_px - x0) * s - 1, ((r + 1) * unit_px - y0) * s - 1],
            outline=ACCENT, width=3,
        )
        out.append(crop)
    return out[0], out[1]


# ---------------------------------------------------------------- statistics and wording


def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson 95% interval for a binomial proportion k/n."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def f_interval(k: int, n: int) -> tuple[float, float, float]:
    """Estimate of overlap² = 1 − 2·p̂1 with the interval mapped from Wilson's interval on p̂1, clipped to [0, 1]."""
    lo, hi = wilson(k, n)
    f = lambda p: min(1.0, max(0.0, 1 - 2 * p))  # noqa: E731
    return f(k / n), f(hi), f(lo)


def verdict(cmp: sp.Comparison) -> str:
    if cmp.mode == "perceptual":
        return "CONTENT CHANGE DETECTED" if cmp.tampered else "NO CONTENT CHANGE DETECTED"
    return "CHANGE DETECTED" if cmp.tampered else "NO CHANGE DETECTED"


def summary_line(cmp: sp.Comparison) -> str:
    """The one sentence a judge reads first."""
    word = UNIT_WORD[cmp.mode]
    n = int(cmp.flagged.sum())
    total = cmp.flagged.size
    if cmp.mode == "perceptual":
        if n:
            return f"{n} of {total} regions look different: their estimated overlap² fell below the threshold."
        return f"All {total} regions stayed above the overlap² threshold: no visible content change was found."
    if n == 0:
        return f"None of the {total:,} {word}s produced a single 1 in {cmp.shots} SWAP-test shots each."
    u = most_suspicious(cmp)
    r, c = unit_rc(cmp, u)
    first = cmp.first_detection.get(u)
    when = f", first on shot {first}" if first else ""
    return (f"{n:,} of {total:,} {word}s read 1 at least once{when}. "
            f"An untouched {word} can never read 1, so each flagged {word} has changed.")


def confidence_text(cmp: sp.Comparison) -> str:
    if cmp.mode == "strict":
        return (f"An untouched tile can never produce a 1 in a noiseless SWAP test. If a tile had changed, the chance "
                f"of missing it in {cmp.shots} shots would be at most {cmp.miss_bound:.1e} (heuristic code bound: "
                f"p1 ≥ {sp.code_info()['p1_min']:.3f} for every changed tile). This is not the probability that the "
                f"image is unchanged.")
    if cmp.mode == "perceptual":
        t = sp.config.PERCEPTUAL_F_THRESHOLD
        return (f"Each region's 64-bit perceptual hash becomes a 6-qubit state. {cmp.shots:,} shots estimate its "
                f"overlap² with the original; a region is flagged when that estimate falls below {t}. Re-saves and "
                f"small tone changes flip few hash bits and usually stay above it; pasted or painted content flips "
                f"many. A small edit can stay under the threshold: use strict mode to catch every change.")
    return ("FRQI (“pixels as angles”) is the textbook baseline. A small edit barely moves the state, so p1 is tiny "
            "and a SWAP test needs millions of shots to notice. That is why SwapPrint uses an error-correcting code.")


# ---------------------------------------------------------------- compare encodings


def fingerprint_problem(fp: sp.Fingerprint) -> str | None:
    """Why an uploaded fingerprint can't be used, or None if it matches the contract's shapes and values."""
    expected = {
        "strict": ((sp.config.STRICT_GRID,) * 2, (sp.config.STRICT_GRID**2, sp.config.STRICT_M)),
        "perceptual": ((sp.config.PERCEPTUAL_GRID,) * 2, (sp.config.PERCEPTUAL_GRID**2, sp.config.PERCEPTUAL_BITS)),
        "frqi": ((sp.config.STRICT_GRID,) * 2, (sp.config.STRICT_GRID**2, sp.config.FRQI_POSITIONS)),
    }
    if fp.mode not in expected:
        return f"unknown mode {fp.mode!r}"
    grid, shape = expected[fp.mode]
    if tuple(fp.grid) != grid or tuple(fp.data.shape) != shape:
        return "its shape doesn't match the mode"
    if fp.mode == "frqi":
        if not np.issubdtype(fp.data.dtype, np.floating) or not np.isfinite(fp.data).all():
            return "its angles aren't finite numbers"
    elif not np.isin(fp.data, (0, 1)).all():
        return "its bits aren't all 0 or 1"
    return None


def encoding_rows(fps_a: dict, fps_b: dict, seed: int) -> list[dict]:
    """The same image pair through all three encodings, each at its default shot budget.

    The shot columns are for the most-changed unit (largest p1), the one that decides how fast an edit is seen.
    """
    rows = []
    for mode in MODES:
        cmp = sp.compare(fps_a[mode], fps_b[mode], seed=seed)
        p1 = float(cmp.p1.max())
        if p1 <= 0:
            first, need99 = None, None
            why = "never (by design)" if mode == "perceptual" else "never (identical)"
        else:
            # perceptual decides by a threshold on the estimated overlap², not by a single 1
            first, why = 1 / p1, None
            need99 = None if mode == "perceptual" else sp.shots_needed(0.01, p1)
        rows.append(dict(
            mode=mode, shots=cmp.shots, min_overlap=float(cmp.overlap.min()), max_p1=p1,
            expected_first=first, shots_99=need99, never=why, detected=cmp.tampered,
            flagged=int(cmp.flagged.sum()), units=int(cmp.flagged.size),
        ))
    return rows


def fmt_shots(v: float | None, never: str | None) -> str:
    if v is None:
        return never or "—"
    if v >= 1e6:
        return f"{v / 1e6:,.1f} million"
    return f"{v:,.1f}" if v < 10 else f"{v:,.0f}"


# ---------------------------------------------------------------- Aer, in a separate process


def run_aer(npz_a: bytes, npz_b: bytes, unit: int, shots: int, kind: str, seed: int, timeout: float = 180) -> dict:
    """sp.circuits.run_swap_test in a child process (app/aer_worker.py). Raises RuntimeError with a short reason."""
    import json
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="swapprint_aer_") as tmp:
        pa, pb = Path(tmp) / "a.npz", Path(tmp) / "b.npz"
        pa.write_bytes(npz_a)
        pb.write_bytes(npz_b)
        cmd = [sys.executable, str(Path(__file__).with_name("aer_worker.py")), str(pa), str(pb),
               str(int(unit)), str(int(shots)), kind, str(int(seed))]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(ROOT))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"the Aer run took longer than {timeout:.0f} s") from exc
    if out.returncode != 0:
        tail = (out.stderr or "").strip().splitlines()[-1:] or [f"exit code {out.returncode}"]
        raise RuntimeError(f"the Aer process failed ({tail[0][:160]})")
    return json.loads(out.stdout.strip().splitlines()[-1])
