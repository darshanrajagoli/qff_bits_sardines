"""Final demo regressions: no-op edits and restored images cannot start a challenge."""

import sys
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402


def button(app, label):
    return next(b for b in app.button if b.label == label)


@pytest.fixture
def app():
    return AppTest.from_file(str(Path(__file__).resolve().parents[1] / "streamlit_app.py"),
                             default_timeout=60).run()


@pytest.mark.parametrize("name", ["brightness", "contrast", "copy_move", "set_pixel", "patch"])
def test_apply_ignores_noop(app, name):
    if name in ("set_pixel", "patch"):
        app.session_state["history"] = [
            {"name": "patch", "params": {"y": 128, "x": 128, "size": 6, "rgb": [255, 32, 32]}}]
    if name == "copy_move":
        app.session_state["loc"] = (255, 255)
    app.selectbox(key="tool").set_value(name).run()
    if name in ("brightness", "contrast"):
        label, value = ("Brightness change", 0) if name == "brightness" else ("Contrast factor", 1.0)
        next(s for s in app.slider if s.label == label).set_value(value)
    history = list(app.session_state["history"])
    button(app, "Apply").click().run()
    assert not app.exception and not app.error
    assert app.session_state["history"] == history
    assert any(w.value == "That edit changes no pixels here. Move the spot or change the settings."
               for w in app.warning)


def test_whitespace_text_falls_back(app):
    app.selectbox(key="tool").set_value("text").run()
    next(t for t in app.text_input if t.label == "Text").set_value("   ")
    button(app, "Apply").click().run()
    assert not app.exception and not app.error
    assert app.session_state["history"][0]["params"]["s"] == "FAKE"
    assert not button(app, "Challenge a friend").disabled


def test_restored_image_cannot_start_challenge(app):
    assert button(app, "Challenge a friend").disabled
    app.session_state["history"] = [
        {"name": "pixel", "params": {"y": 128, "x": 128, "channel": 0, "delta": delta}}
        for delta in (1, -1)]
    app.run()
    assert not app.exception and not app.error
    assert len(app.session_state["history"]) == 2
    assert button(app, "Challenge a friend").disabled


@pytest.mark.parametrize("shots", [1, 2])
def test_summary_shots_and_first_hit_scope(shots):
    base = core.load_artwork("hokusai_great_wave.png")
    fp = core.sp.fingerprint(base, "strict")
    cmp = core.sp.compare(fp, fp, shots=shots, seed=0)
    assert f"{shots} SWAP-test {'shot' if shots == 1 else 'shots'} each" in core.summary_line(cmp)
    assert f"in {shots} {'shot' if shots == 1 else 'shots'} would" in core.confidence_text(cmp)
    cmp.flagged.flat[0] = True
    cmp.p1.flat[0] = 0.25
    cmp.first_detection[0] = shots
    assert f"on the most suspicious tile, the first 1 came on shot {shots}" in core.summary_line(cmp)
