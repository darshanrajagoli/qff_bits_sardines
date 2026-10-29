"""The How it works pictures come from one real tile and fit every grid position (run: pytest app/tests)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402

sp = core.sp


@pytest.fixture(scope="module")
def art():
    img = sp.synthetic.artwork(seed=0)
    return img, sp.fingerprint(img, "strict")


@pytest.mark.parametrize("rc", [(0, 0), (32, 32), (63, 63), (1, 62)])
def test_step_visuals_any_tile(art, rc):
    img, fp = art
    v = core.step_visuals(img, fp, *rc)
    assert {k: im.size for k, im in v.items()} == {"canon": (256, 256), "zoom": (256, 256),
                                                    "code": (256, 128), "signs": (256, 128)}
    assert core.data_uri(v["code"]).startswith("data:image/png;base64,")


def test_codeword_picture_is_the_tiles_codeword(art):
    img, fp = art
    code = np.asarray(core.step_visuals(img, fp, 5, 7)["code"])[::4, ::4]  # undo the x4 upscale
    bits = np.asarray(fp.data[5 * fp.grid[1] + 7], dtype=np.uint8).reshape(32, 64)
    assert np.array_equal(code[..., 0] == 0xA5, bits == 1)  # purple 50 (#a56eff) marks a 1
