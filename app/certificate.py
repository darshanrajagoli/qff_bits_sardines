"""Render a portable PNG record of a SwapPrint comparison."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import swapprint
from swapprint import Comparison, style


TOKENS = style.tokens("g100")
BACKGROUND = TOKENS["background"]
TEXT = TOKENS["text-primary"]
MUTED = TOKENS["text-secondary"]
PANEL = TOKENS["layer-01"]
BORDER = TOKENS["border-subtle-00"]
FOOTER = (
    "An unsigned integrity record, not a signature or watermark. "
    "“No change detected” is not proof that nothing changed."
)
CREDIT = "SwapPrint · team sardines. Type: Departure Mono (OFL 1.1)."


def _font(size):
    """Load bundled Departure Mono, retaining rendering when it is missing."""
    path = Path(__file__).resolve().parent / "static" / "fonts" / "DepartureMono-Regular.otf"
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError:
        pass
    return ImageFont.load_default(size=size)


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
    fonts = {size: _font(size) for size in (11, 22, 33)}

    def text(x, y, value, size=11, fill=TEXT, font=None):
        draw.text((x, y), value, font=font or fonts[size], fill=fill, anchor="lt")

    text(40, 32, "SwapPrint verification record", font=fonts[33])
    draw.line((40, 80, 1160, 80), fill=style.PURPLE, width=1)

    title_lines = _wrap(draw, artwork_title, fonts[22], 1120)
    if len(title_lines) > 3:
        title_lines = title_lines[:3]
        last = title_lines[-1]
        while last and draw.textlength(last + "…", font=fonts[22]) > 1120:
            last = last[:-1]
        title_lines[-1] = last + "…"
    for index, line in enumerate(title_lines):
        text(40, 96 + index * 24, line, font=fonts[22])

    noun = "CONTENT CHANGE" if cmp.mode == "perceptual" else "CHANGE"
    verdict = f"{noun} DETECTED" if cmp.tampered else f"NO {noun} DETECTED"
    text(40, 192, verdict, fill=style.ALERT_ON_DARK if cmp.tampered else TEXT,
         font=fonts[33])

    thumbnails = [("Original", Image.fromarray(original)), ("Checked", Image.fromarray(checked))]
    if heatmap_img is not None:
        thumbnails.append(("Heatmap", heatmap_img))
    for index, (label, source) in enumerate(thumbnails):
        x = 40 + index * 256
        text(x, 248, label, fill=style.ACCENT_ON_DARK)
        draw.rectangle((x, 272, x + 223, 495), fill=PANEL, outline=BORDER, width=1)
        thumb = source.convert("RGBA")
        thumb.thumbnail((208, 208), Image.Resampling.LANCZOS)
        position = (x + 8 + (208 - thumb.width) // 2, 280 + (208 - thumb.height) // 2)
        card.paste(thumb, position, thumb)

    draw.rectangle((808, 240, 1159, 511), fill=PANEL, outline=BORDER, width=1)
    backend = ("Exact backend", "analytical sampler") if cmp.backend == "exact" else ("Backend", cmp.backend)
    details = [
        ("Mode", cmp.mode, fonts[11]),
        (*backend, fonts[11]),
        ("Shots per unit", str(cmp.shots), fonts[11]),
        ("Flagged units", f"{np.count_nonzero(cmp.flagged)} out of {np.size(cmp.flagged)}", fonts[11]),
        ("Date/time", when.isoformat(sep=' ', timespec='seconds'), fonts[11]),
        ("SwapPrint", swapprint.__version__, fonts[11]),
    ]
    y = 256
    for label, value, font in details:
        prefix = f"{label}: " if label != "SwapPrint" else f"{label} "
        text(824, y, prefix, fill=style.ACCENT_ON_DARK)
        offset = draw.textlength(prefix, font=fonts[11])
        if draw.textlength(value, font=font) > 320 - offset:
            y += 24
            offset = 0
        for line in _wrap(draw, value, font, 320 - offset):
            text(824 + offset, y, line, font=font)
            y += 24
        y += 8

    if cmp.miss_bound is not None:
        draw.rectangle((40, 528, 1159, 591), fill=PANEL, outline=BORDER, width=1)
        text(56, 536, "heuristic miss bound P(no detection | a tile changed)", fill=style.ACCENT_ON_DARK)
        text(56, 560, f"{cmp.miss_bound:.1e}", font=fonts[22])

    draw.line((40, 608, 1160, 608), fill=BORDER, width=1)
    for index, line in enumerate(_wrap(draw, FOOTER, fonts[11], 1120)):
        text(40, 624 + index * 16, line, 11, MUTED)
    text(40, 648, CREDIT, 11, MUTED)

    output = BytesIO()
    card.save(output, format="PNG")
    return output.getvalue()
