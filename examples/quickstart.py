"""Quickstart: fingerprint an artwork, change one pixel by 1, and catch the change with SWAP tests.

    python examples/quickstart.py [image]

Without an argument it uses a synthetic artwork. Strict mode catches the edit within a few shots; the FRQI baseline
("pixels as angles") would need millions of shots; perceptual mode ignores it on purpose.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import swapprint as sp
except ModuleNotFoundError:  # running from a checkout without `pip install -e .`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import swapprint as sp

SHOTS, SEED = 32, 0


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # code_info's note has symbols that Windows' cp1252 pipes cannot print
    if len(sys.argv) > 1:
        img, source = sp.load_image(sys.argv[1]), sys.argv[1]
    else:
        img, source = sp.synthetic.artwork(), "synthetic.artwork(seed=0)"
    edited = sp.edits.apply(img, "pixel")
    print(f"swapprint {sp.__version__} on {source}: edit 'pixel' (red of pixel (128, 128) changed by 1)")
    print(f"compare(seed={SEED}, backend='exact'): strict/frqi {SHOTS} shots, perceptual {sp.config.PERCEPTUAL_SHOTS} shots")
    print(f"perceptual: 16 regions of 64x64, F threshold {sp.config.PERCEPTUAL_F_THRESHOLD}; FRQI: 64 positions (48 values + 16 padding)\n")

    header = f"{'mode':<11}{'units':>6}{'min overlap':>14}{'max p1':>12}{'flagged':>9}{'tampered':>10}{'first 1 at':>12}"
    print(header)
    print("-" * len(header))
    results = {}
    for mode in ("strict", "perceptual", "frqi"):
        shots = sp.config.PERCEPTUAL_SHOTS if mode == "perceptual" else SHOTS
        cmp = sp.compare(sp.fingerprint(img, mode), sp.fingerprint(edited, mode), shots=shots, seed=SEED)
        results[mode] = cmp
        firsts = [s for s in cmp.first_detection.values() if s is not None]
        first = f"shot {min(firsts)}" if firsts else "-"
        print(
            f"{mode:<11}{cmp.overlap.size:>6}{cmp.overlap.min():>14.7f}{cmp.p1.max():>12.5g}"
            f"{int(cmp.flagged.sum()):>9}{str(cmp.tampered):>10}{first:>12}"
        )

    info = sp.code_info()
    print("\ncode_info():")
    for key, value in info.items():
        print(f"  {key}: {value}")
    k = sp.shots_needed(1e-6, info["p1_min"])
    print(f"\nshots_needed(1e-6, p1_min) = {k}: {k} shots miss a changed strict tile with probability <= 1e-6")
    print(f"strict miss_bound at {SHOTS} shots = {results['strict'].miss_bound:.3g}")

    p1 = float(results["frqi"].p1.max())
    if p1 > 0:
        print(
            f"\nfrqi baseline: the changed tile has p1 = {p1:.3g}, so the first 1 takes about 1/p1 = {1 / p1:,.0f} shots,"
            f"\nand a 1e-6 miss chance needs shots_needed(1e-6, p1) = {sp.shots_needed(1e-6, p1):,} shots"
        )


if __name__ == "__main__":
    main()
