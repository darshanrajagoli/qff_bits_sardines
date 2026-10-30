"""The Tamper crosshair preserves the artwork, keeps the chosen pixel visible and clips safely at the corners."""

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

PURPLE, DARK = core._rgb(core.sp_style.PURPLE), (22, 22, 22)


@pytest.mark.parametrize("size", [256, 512, 768])
@pytest.mark.parametrize("canon", [128, 256])
def test_mark_point_preserves_image_and_marks_pixel(size, canon):
    pic = Image.new("RGB", (size, size), (74, 115, 156))
    before = pic.tobytes()
    y, x = 41, 103
    marked = core.mark_point(pic, y, x, canon=canon)

    assert marked is not pic
    assert marked.size == pic.size
    assert pic.tobytes() == before

    cx, cy = int((x + 0.5) * size / canon), int((y + 0.5) * size / canon)
    assert marked.getpixel((cx, cy)) == pic.getpixel((cx, cy))  # the gap leaves the chosen pixel visible
    mid = round(size * 0.016) + round(size * 0.06) // 2  # half-way along each arm
    for dx, dy in ((-mid, 0), (mid, 0), (0, -mid), (0, mid)):
        assert marked.getpixel((cx + dx, cy + dy)) == PURPLE


def test_mark_point_outlines_arms():
    pic = Image.new("RGB", (768, 768), "white")
    marked = core.mark_point(pic, 41, 103)
    cx, cy = int(103.5 * 3), int(41.5 * 3)
    mid = round(768 * 0.016) + round(768 * 0.06) // 2
    half = round(768 * 0.012) // 2
    # just outside the right arm, above and below it: dark outline, not white
    assert marked.getpixel((cx + mid, cy - half - 1)) == DARK
    assert marked.getpixel((cx + mid, cy + half + 1)) == DARK


@pytest.mark.parametrize("y, x", [(0, 0), (255, 255)])
def test_mark_point_corners(y, x):
    pic = Image.new("RGB", (768, 768), (74, 115, 156))
    marked = core.mark_point(pic, y, x)
    assert marked.size == pic.size
    centre = (3 * x + 1, 3 * y + 1)
    assert marked.getpixel(centre) == pic.getpixel(centre)
