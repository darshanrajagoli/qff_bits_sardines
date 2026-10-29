"""Facts and art assets for the video, computed with the same library the app uses (run with the repo .venv).

    .venv/Scripts/python.exe video/probe.py [artwork.png] [seed] [out_dir]

Writes <out_dir>/facts.json (the numbers the narration quotes, so they match what the app shows) and
<out_dir>/art.png (canonical 256x256 artwork), <out_dir>/mosaic.png (64x64 strict fingerprint mosaic).
Called by record.py; finish.py and media.py only read its output.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import core  # noqa: E402  (app/core.py: pure helpers, no Streamlit)
import swapprint as sp  # noqa: E402


def main() -> None:
    art = sys.argv[1] if len(sys.argv) > 1 else "hokusai_great_wave.png"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent / "out" / "raw"
    out.mkdir(parents=True, exist_ok=True)

    base = core.load_artwork(art)
    step = core.surprise(seed, 0)                      # what "Surprise me" does first, at this seed
    edited = core.replay(base, [step])
    fps_a = {m: sp.fingerprint(base, mode=m) for m in core.MODES}
    fps_b = {m: sp.fingerprint(edited, mode=m) for m in core.MODES}
    rows = {r["mode"]: r for r in core.encoding_rows(fps_a, fps_b, seed)}
    cmp = sp.compare(fps_a["strict"], fps_b["strict"], backend="exact", seed=seed)
    unit = core.most_suspicious(cmp)
    traced = [u for u in cmp.traces if cmp.p1.flat[u] > 0]
    first = cmp.first_detection.get(traced[0]) if traced else None

    def n(v):
        return None if v is None else float(v)

    facts = {
        "artwork": art, "seed": seed, "edit": step, "edit_text": core.describe(step),
        "truth": [step["params"]["y"], step["params"]["x"]],
        "tile_rc": list(core.unit_rc(cmp, unit)), "tiles": int(cmp.flagged.size),
        "strict_shots": int(cmp.shots), "strict_first_shot": first, "strict_p1": n(cmp.p1.max()),
        "strict_tampered": bool(cmp.tampered),
        "strict_expected_first": n(rows["strict"]["expected_first"]), "strict_99": n(rows["strict"]["shots_99"]),
        "frqi_expected_first": n(rows["frqi"]["expected_first"]), "frqi_99": n(rows["frqi"]["shots_99"]),
        "frqi_p1": n(rows["frqi"]["max_p1"]), "frqi_detected": bool(rows["frqi"]["detected"]),
        "frqi_min_overlap": n(rows["frqi"]["min_overlap"]),
        # the edited tile's real codewords (2,048 bits each, packed, hex) for the diagram
        "codeword_a": np.packbits(np.asarray(fps_a["strict"].data[unit], dtype=np.uint8)).tobytes().hex(),
        "codeword_b": np.packbits(np.asarray(fps_b["strict"].data[unit], dtype=np.uint8)).tobytes().hex(),
        "tile_rgb_a": base[(unit // cmp.grid[1]) * 4:(unit // cmp.grid[1]) * 4 + 4, (unit % cmp.grid[1]) * 4:(unit % cmp.grid[1]) * 4 + 4].tolist(),
        "pixel_before": base[step["params"]["y"], step["params"]["x"]].tolist(),
        "pixel_after": edited[step["params"]["y"], step["params"]["x"]].tolist(),
    }
    (out / "facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    Image.fromarray(base).save(out / "art.png")
    Image.fromarray(core.mosaic(fps_a["strict"])).save(out / "mosaic.png")
    Image.fromarray(core.mosaic(fps_b["strict"])).save(out / "mosaic_edited.png")
    print({k: v for k, v in facts.items() if not k.startswith('codeword')})


if __name__ == "__main__":
    main()
