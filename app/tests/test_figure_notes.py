"""Every Results figure has a plain-language note, short and free of overclaims (run: pytest app/tests)."""

import json
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
FIG = APP.parent / "experiments" / "figures"
NOTES = json.loads((APP / "figure_notes.json").read_text(encoding="utf-8"))


def _figures():
    keys = set()
    for name in ("captions.json", "core_captions.json"):
        path = FIG / name
        if path.exists():
            keys |= set(json.loads(path.read_text(encoding="utf-8")))
    return keys


def test_every_figure_has_a_note():
    missing = sorted(_figures() - set(NOTES))
    assert not missing, f"add plain-language notes to app/figure_notes.json for: {missing}"


def test_notes_are_short_and_honest():
    banned = re.compile(r"\b(secure|proof|proves|proven|tamper-proof|watermark|signature|quantum advantage)\b", re.I)
    for png, note in NOTES.items():
        assert note["title"].strip() and note["plain"].strip(), png
        assert len(note["plain"].split()) <= 45, png
        assert not banned.search(note["title"] + " " + note["plain"]), png
