"""Render a portable PNG record of a SwapPrint comparison."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import swapprint
from swapprint import Comparison


BACKGROUND = "#111318"
ACCENT = "#E841D6"
TEXT = "#E6E8EE"
MUTED = "#9AA0AB"
FOOTER = (
    "An integrity check, not a signature or watermark. "
    "“No change detected” is not proof that nothing changed."
)


def _wrap(draw, text, font, width):
    """Wrap by measured width, including titles with no spaces."""
    lines = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}" if line else word
        if draw.textlength(candidate, font=font) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ""
        for char in word:
            if line and draw.textlength(line + char, font=font) > width:
                lines.append(line)
                line = ""
            line += char
    if line:
        lines.append(line)
    return lines


def make_certificate(
    original: np.ndarray,
    checked: np.ndarray,
    cmp: Comparison,
    *,
    artwork_title: str,
    when: datetime,
    heatmap_img: Image.Image | None = None,
) -> bytes:
    """Return a 1200 × 675 PNG with the supplied comparison's verdict.

    Images are canonical uint8 RGB arrays. The optional heatmap is fitted
    without changing its aspect ratio or modifying the caller's image.
    """
    card = Image.new("RGB", (1200, 675), BACKGROUND)
    draw = ImageDraw.Draw(card)
    fonts = {size: ImageFont.load_default(size=size) for size in (16, 18, 20, 22, 32, 36)}

    def text(x, y, value, size=20, fill=TEXT):
        draw.text((x, y), value, font=fonts[size], fill=fill, anchor="lt")

    text(40, 30, "SwapPrint verification record", 32)
    draw.line((40, 76, 1160, 76), fill=ACCENT, width=2)

    title_lines = _wrap(draw, artwork_title, fonts[22], 1120)
    if len(title_lines) > 3:
        title_lines = title_lines[:3]
        last = title_lines[-1]
        while last and draw.textlength(last + "…", font=fonts[22]) > 1120:
            last = last[:-1]
        title_lines[-1] = last + "…"
    for index, line in enumerate(title_lines):
        text(40, 92 + index * 26, line, 22)

    noun = "CONTENT CHANGE" if cmp.mode == "perceptual" else "CHANGE"
    verdict = f"{noun} DETECTED" if cmp.tampered else f"NO {noun} DETECTED"
    text(40, 188, verdict, 36, ACCENT if cmp.tampered else TEXT)

    thumbnails = [("Original", Image.fromarray(original)), ("Checked", Image.fromarray(checked))]
    if heatmap_img is not None:
        thumbnails.append(("Heatmap", heatmap_img))
    for index, (label, source) in enumerate(thumbnails):
        x = 40 + index * 260
        text(x, 250, label, 18, MUTED)
        thumb = source.convert("RGBA")
        thumb.thumbnail((224, 224), Image.Resampling.LANCZOS)
        position = (x + (224 - thumb.width) // 2, 280 + (224 - thumb.height) // 2)
        card.paste(thumb, position, thumb)
        draw.rectangle((x - 1, 279, x + 224, 504), outline=MUTED)

    backend = "exact backend: analytical sampler" if cmp.backend == "exact" else cmp.backend
    details = [
        f"Mode: {cmp.mode}",
        backend,
        f"Shots per unit: {cmp.shots}",
        f"Flagged units: {np.count_nonzero(cmp.flagged)} out of {np.size(cmp.flagged)}",
        f"Date/time: {when.isoformat(sep=' ', timespec='seconds')}",
        f"SwapPrint {swapprint.__version__}",
    ]
    y = 250
    for detail in details:
        for line in _wrap(draw, detail, fonts[18], 320):
            text(840, y, line, 18)
            y += 23
        y += 9

    if cmp.miss_bound is not None:
        text(40, 537, "heuristic miss bound P(no detection | a tile changed)", 18, MUTED)
        text(40, 564, f"{cmp.miss_bound:.1e}", 22, ACCENT)

    draw.line((40, 609, 1160, 609), fill=MUTED)
    for index, line in enumerate(_wrap(draw, FOOTER, fonts[16], 1120)):
        text(40, 628 + index * 20, line, 16, MUTED)

    output = BytesIO()
    card.save(output, format="PNG")
    return output.getvalue()
