"""The pinned demo scenarios keep their verdicts (run: pytest app/tests)."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

sp = core.sp
SCEN = json.loads((Path(__file__).resolve().parents[1] / "demo_scenarios.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("sc", SCEN["scenarios"], ids=lambda s: s["id"])
def test_scenario_verdict(sc):
    base = core.load_artwork(sc["artwork"])
    edited = core.replay(base, sc["edits"])
    fa, fb = sp.fingerprint(base, sc["mode"]), sp.fingerprint(edited, sc["mode"])
    thresholds = [None, 0.52, 0.65] if sc["mode"] == "perceptual" else [None]
    for t in thresholds:
        for seed in range(20):
            cmp = sp.compare(fa, fb, seed=seed, threshold=t)
            assert cmp.tampered == sc["expect_tampered"], (sc["id"], t, seed)


def test_game_flags_the_hidden_spot():
    g = SCEN["game"]
    base = core.load_artwork(g["artwork"])
    step = core.surprise(g["seed"], g["surprise_index"])
    edited = core.replay(base, [step])
    cmp = sp.compare(sp.fingerprint(base, "strict"), sp.fingerprint(edited, "strict"), seed=g["seed"])
    y, x = step["params"]["y"], step["params"]["x"]
    assert cmp.tampered and int(cmp.flagged.sum()) == 1
    assert cmp.flagged[y // 4, x // 4]
    assert core.most_suspicious(cmp) == (y // 4) * 64 + x // 4


def test_surprise_is_repeatable_and_imperceptible():
    assert core.surprise(3, 1) == core.surprise(3, 1)
    base = core.load_artwork("hokusai_great_wave.png")
    diff = np.abs(core.replay(base, [core.surprise(0, 0)]).astype(int) - base.astype(int))
    assert diff.sum() == 1


def test_wilson_and_upload_edge_cases():
    lo, hi = core.wilson(0, 32)
    assert lo == 0 and 0.09 < hi < 0.12
    from io import BytesIO

    from PIL import Image

    for im in (Image.new("I;16", (300, 200), 40000), Image.new("CMYK", (64, 64)), Image.new("RGBA", (500, 300))):
        buf = BytesIO()
        im.save(buf, format="TIFF" if im.mode != "RGBA" else "PNG")
        img, notes = core.load_upload(buf.getvalue())
        assert img.shape == (256, 256, 3) and img.dtype == np.uint8
    with pytest.raises(ValueError):
        core.load_upload(b"not an image")


def test_fingerprint_validation():
    img = sp.synthetic.artwork(seed=0)
    for mode in ("strict", "perceptual", "frqi"):
        assert core.fingerprint_problem(sp.fingerprint(img, mode)) is None
    fp = sp.fingerprint(img, "perceptual")
    bad = sp.Fingerprint(mode="perceptual", q=6, grid=(4, 4), unit_px=64, data=fp.data * 2, version=fp.version)
    assert core.fingerprint_problem(bad)
    assert core.fingerprint_problem(sp.Fingerprint(mode="x", q=6, grid=(4, 4), unit_px=64, data=fp.data, version=""))


def test_challenge_scoring():
    base = core.load_artwork("hokusai_great_wave.png")
    edited = core.replay(base, [{"name": "patch", "params": {"y": 100, "x": 50, "size": 6, "rgb": [255, 0, 0]}}])
    assert core.changed_box(base, edited) == (100, 50, 106, 56)
    assert core.guess_distance(base, edited, (102, 52)) == 0
    assert core.guess_distance(base, edited, (100, 60)) == 5
    assert core.changed_box(base, base) is None and core.guess_distance(base, base, (0, 0)) is None
    assert "global" in core.describe_box((0, 0, 256, 256))
    assert core.describe_box((5, 7, 6, 8)) == "at row 5, column 7"
