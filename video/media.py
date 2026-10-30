"""README media: docs/media/hero.png (1600x600 Carbon banner) and docs/media/teaser.gif (the key moment, from the video).

    video/.venv/Scripts/python.exe video/media.py          # after record.py (art) and finish.py (video)

Hero: the app's light theme, Departure/Plex Mono, and the real Great Wave turning into its
real strict-mode fingerprint mosaic, with the tile the demo edits ringed in Magenta 50.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = HERE / "out" / "raw"
MEDIA = ROOT / "docs" / "media"
FONTS = ROOT / "swapprint" / "fonts"
S = 2                                             # draw at 2x, downsample for clean edges

WHITE, LAYER, TXT, TXT2, HELP = "#ffffff", "#f4f4f4", "#161616", "#525252", "#6f6f6f"
PURPLE, MAGENTA, GRID = "#8a3ffc", "#ee5396", (138, 63, 252)
GRAD = [(255, 126, 182), (238, 83, 150), (138, 63, 252)]   # q-bits.in .text-gradient: 0 %, 42 %, 100 %


def f(name, size):
    path = (HERE / "assets/DepartureMono-Regular.otf" if name == "IBMPlexSans-SemiBold" else
            FONTS / f"{'IBMPlexMono-Regular' if name == 'IBMPlexSans-Regular' else name}.ttf")
    return ImageFont.truetype(str(path), size * S)


def wrapped(draw, text, xy, font, width, line_height, fill):
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and draw.textlength(candidate, font=font) > width * S:
            lines.append(line)
            line = word
        else:
            line = candidate
    lines.append(line)
    for i, line in enumerate(lines):
        draw.text((xy[0] * S, (xy[1] + i * line_height) * S), line, font=font, fill=fill)


def hero(output: Path | None = None) -> Path:
    w, h = 1600, 600
    im = Image.new("RGB", (w * S, h * S), WHITE)
    d = ImageDraw.Draw(im, "RGBA")
    for x in range(12, w, 24):
        for y in range(12, h, 24):
            d.rectangle((x*S,y*S,(x+1)*S,(y+1)*S),fill=(82,82,82,24))
    frame=[(40,24),(1560,24),(1576,40),(1576,560),(1560,576),(40,576),(24,560),(24,40),(40,24)]
    d.line([(x*S,y*S) for x,y in frame],fill=(198,198,198,255),width=2*S)
    x0 = 64
    d.text((x0 * S, 76 * S), "Qiskit Fall Fest 2026 · Problem 5 · Quantum Fingerprint",
           font=f("IBMPlexSans-Regular", 18), fill=TXT2)
    for i in range(160):
        v = i / 159
        a, b, t = (GRAD[0], GRAD[1], v / 0.42) if v < 0.42 else (GRAD[1], GRAD[2], (v - 0.42) / 0.58)
        col = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
        d.rectangle([(x0 + i) * S, 132 * S, (x0 + i + 1) * S, 138 * S], fill=col)
    d.text(((x0 - 6) * S, 178 * S), "SwapPrint", font=f("IBMPlexSans-SemiBold", 112), fill=TXT)
    d.text((x0 * S, 318 * S), "Quantum fingerprints for digital art", font=f("IBMPlexSans-Regular", 32), fill=TXT2)
    wrapped(d,"Every 4×4 tile becomes an 11-qubit state. A SWAP test explores what changed.",
            (x0,382),f("IBMPlexSans-Regular",20),780,30,HELP)
    d.text((x0 * S, 508 * S), "SwapPrint", font=f("IBMPlexSans-SemiBold", 18), fill=TXT)
    bw = d.textlength("SwapPrint", font=f("IBMPlexSans-SemiBold", 18))
    d.text((x0 * S + bw + 12 * S, 508 * S), "·  team sardines", font=f("IBMPlexSans-Regular", 18), fill=HELP)

    # the motif: the real artwork, tile by tile, turning into its real fingerprint mosaic along a diagonal
    art = np.asarray(Image.open(RAW / "art.png").convert("RGB").resize((64, 64), Image.BOX))
    mos = np.asarray(Image.open(RAW / "mosaic.png").convert("RGB"))
    facts = json.loads((RAW / "facts.json").read_text(encoding="utf-8"))
    ii, jj = np.mgrid[0:64, 0:64]
    t = np.clip((ii + jj - 52) / 24, 0, 1)[..., None]
    tiles = (art * (1 - t) + mos * t).astype(np.uint8)
    size, mx, my = 432, 1032, 72
    im.paste(Image.fromarray(tiles).resize((size * S, size * S), Image.NEAREST), (mx * S, my * S))
    ty, tx = facts["truth"]
    cell = size / 64
    cx, cy = mx + (tx // 4) * cell, my + (ty // 4) * cell
    d.rectangle([(cx - 5) * S, (cy - 5) * S, (cx + cell + 5) * S, (cy + cell + 5) * S], outline=MAGENTA, width=3 * S)
    wrapped(d,"The Great Wave (Hokusai, The Met, public domain) → its strict-mode fingerprint mosaic",
            (mx,my+size+10),f("IBMPlexSans-Regular",14),432,18,HELP)
    out = output if output is not None else MEDIA / "hero.png"
    im.resize((w, h), Image.LANCZOS).save(out, optimize=True)
    return out


def teaser() -> Path:
    tl = json.loads((HERE / "out" / "timeline_resolved.json").read_text(encoding="utf-8"))
    seg = {s["id"]: s for s in tl["segments"]}
    a = seg["shots"]["start"] + seg["shots"]["dur"] - 3.0        # shots stream in, the first 1 lands
    b = seg["heatmap"]["start"] + 4.6                              # ...then the heatmap zooms onto the tile
    out = MEDIA / "teaser.gif"
    vf = ("fps=12,scale=720:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128:stats_mode=diff[p];"
          "[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.2f}", "-t", f"{b - a:.2f}",
                    "-i", str(HERE / "out" / "swapprint_demo.mp4"), "-vf", vf, "-loop", "0", str(out)], check=True)
    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hero-only", action="store_true", help="Preview the banner without refreshing the teaser")
    parser.add_argument("--output", type=Path, help="Banner preview path; requires --hero-only")
    args = parser.parse_args()
    if args.output and not args.hero_only:
        parser.error("--output requires --hero-only")
    MEDIA.mkdir(parents=True, exist_ok=True)
    for p in ((hero(args.output),) if args.hero_only else (hero(), teaser())):
        print(f"wrote {p} ({p.stat().st_size / 1e6:.2f} MB)")
