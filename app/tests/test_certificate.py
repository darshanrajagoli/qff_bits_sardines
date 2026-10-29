"""The comparison record renders without external artwork or font files."""

import sys
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from certificate import make_certificate  # noqa: E402

import swapprint as sp  # noqa: E402


@pytest.fixture(scope="module")
def artwork():
    return sp.synthetic.artwork(seed=0)


def assert_png(data):
    assert isinstance(data, bytes)
    with Image.open(BytesIO(data)) as image:
        assert image.format == "PNG"
        assert image.size == (1200, 675)
        image.load()
        assert image.getpixel((0, 0)) == (17, 19, 24)


@pytest.mark.parametrize("mode", ["strict", "perceptual", "frqi"])
@pytest.mark.parametrize("edited", [False, True], ids=["identical", "pixel-edit"])
def test_comparison_certificate(artwork, mode, edited):
    checked = sp.edits.apply(artwork, "pixel") if edited else artwork.copy()
    comparison = sp.compare(sp.fingerprint(artwork, mode), sp.fingerprint(checked, mode), seed=0)
    if mode == "strict":
        assert comparison.tampered == edited
    assert_png(make_certificate(
        artwork, checked, comparison,
        artwork_title="Synthetic artwork",
        when=datetime(2026, 10, 29, 16, 30, tzinfo=timezone.utc),
    ))


@pytest.mark.parametrize("title", [("A long artwork title " * 10)[:200], "X" * 200])
def test_long_title_with_heatmap_and_aer_label(artwork, title):
    fingerprint = sp.fingerprint(artwork, "strict")
    comparison = replace(sp.compare(fingerprint, fingerprint, seed=0), backend="aer")
    heatmap = Image.new("RGBA", (512, 128), (232, 65, 214, 128))
    original_pixels = artwork.copy()
    heatmap_pixels = heatmap.tobytes()
    assert len(title) == 200
    assert_png(make_certificate(
        artwork, artwork, comparison,
        artwork_title=title,
        when=datetime(2026, 10, 29, 16, 30),
        heatmap_img=heatmap,
    ))
    np.testing.assert_array_equal(artwork, original_pixels)
    assert heatmap.tobytes() == heatmap_pixels
