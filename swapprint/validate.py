"""Reproducible C1 circuit validation: python -m swapprint.validate.

Fixed image/edit and shot seeds reproduce statistics (wall times may differ).
Each kind runs 50 unit pairs at 2048 shots; no outcomes are selected for coverage.
"""
from __future__ import annotations

import csv
from pathlib import Path
from time import perf_counter

import numpy as np

from . import circuits, edits, synthetic
from .compare import overlaps
from .fingerprint import fingerprint

SEED = 20261029
SHOTS = 2048
FIELDS = ["mode", "kind", "pair_type", "unit", "p1_exact", "ones", "shots", "p1_est",
          "wilson_lo", "wilson_hi", "inside", "qubits", "seconds"]


def wilson(ones, shots):
    """Two-sided Wilson score interval, 95%, including p=0 and p=1."""
    z = 1.959963984540054
    p = ones / shots
    denominator = 1 + z**2 / shots
    centre = (p + z**2 / (2 * shots)) / denominator
    half = z * np.sqrt(p * (1 - p) / shots + z**2 / (4 * shots**2)) / denominator
    return max(0.0, float(centre - half)), min(1.0, float(centre + half))


def _pairs():
    # Every edited strict pair measures the tile containing the edited pixel.
    for i in range(10):
        img = synthetic.artwork(100 + i)
        a = fingerprint(img, "strict")
        yield "identical", a, a, i * 65
        b = fingerprint(edits.pixel(img, y=128, x=128), "strict")
        yield "pixel", a, b, 32 * 64 + 32
        b = fingerprint(synthetic.artwork(300 + i), "strict")
        yield "unrelated", a, b, i * 65

    # Select image/edit by exact overlap alone, before sampling, to spread p1.
    # Median-split hashes have 31 set bits, so two nonflat hashes differ in an
    # even number of positions: the lowest nonzero attainable p1 is 0.060546875.
    candidates = []
    for i in range(20):
        img = synthetic.artwork(500 + i)
        a = fingerprint(img, "perceptual")
        for size in (2, 4, 6, 8, 12, 16, 24, 32, 40, 48):
            for label in ("copy_move", "patch"):
                if label == "copy_move":
                    edited = edits.copy_move(img, src=(180, 180), dst=(72, 72), size=size)
                else:
                    edited = edits.patch(img, y=72, x=72, size=size)
                b = fingerprint(edited, "perceptual")
                p1 = float((1 - overlaps(a, b).ravel()[5] ** 2) / 2)
                if 0.015 <= p1 <= 0.42:
                    candidates.append((p1, label, a, b))
    for target in np.linspace(0.02, 0.4, 10):
        if not candidates:
            raise RuntimeError("not enough intermediate perceptual pairs")
        best = min(range(len(candidates)), key=lambda j: abs(candidates[j][0] - target))
        _, label, a, b = candidates.pop(best)
        yield label, a, b, 5

    for i in range(10):
        img = synthetic.artwork(700 + i)
        a = fingerprint(img, "frqi")
        if i < 2:
            label, b = "identical", a
        elif i < 5:
            label, b = "pixel", fingerprint(edits.pixel(img), "frqi")
        else:
            label = "patch"
            b = fingerprint(edits.patch(img, y=128, x=128, size=4), "frqi")
        yield label, a, b, 32 * 64 + 32


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    start = perf_counter()
    root = Path(__file__).resolve().parents[1] / "experiments"
    results, figures = root / "results", root / "figures"
    results.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, (pair_type, a, b, unit) in enumerate(_pairs()):
        for k, kind in enumerate(("ancilla", "destructive")):
            run = circuits.run_swap_test(a, b, unit, shots=SHOTS, kind=kind, seed=SEED + 2 * index + k)
            lo, hi = wilson(run["ones"], SHOTS)
            rows.append(dict(mode=a.mode, kind=kind, pair_type=pair_type, unit=unit,
                             **{key: run[key] for key in ("p1_exact", "ones", "shots", "p1_est", "qubits", "seconds")},
                             wilson_lo=lo, wilson_hi=hi, inside=lo <= run["p1_exact"] <= hi))
        if (index + 1) % 10 == 0:
            print(f"Validated {2 * (index + 1)}/100 circuits ({perf_counter() - start:.1f} s)", flush=True)
    _write_csv(results / "core_validation.csv", rows)
    _write_csv(figures / "core_validation_data.csv", rows)
    fig, axes = plt.subplots(1, 2, figsize=(10.6, 4.8), sharex=True, sharey=True)
    styles = {"strict": ("#0072B2", "o"), "perceptual": ("#D55E00", "s"), "frqi": ("#009E73", "^")}
    for ax, kind in zip(axes, ("ancilla", "destructive")):
        ax.plot([0, 0.52], [0, 0.52], color="0.4", linestyle="--", linewidth=1, label="y = x")
        for mode, (color, marker) in styles.items():
            group = [r for r in rows if r["mode"] == mode and r["kind"] == kind]
            x = np.array([r["p1_exact"] for r in group])
            y = np.array([r["p1_est"] for r in group])
            errors = [y - [r["wilson_lo"] for r in group], [r["wilson_hi"] for r in group] - y]
            ax.errorbar(x, y, yerr=errors, fmt=marker, ms=5, color=color, capsize=2,
                        alpha=0.8, elinewidth=1, label=mode)
        ax.set(title=kind.capitalize(), xlabel="Exact P(1)", xlim=(-0.015, 0.53), ylim=(-0.015, 0.55))
        ax.grid(alpha=0.2)
        ax.set_aspect("equal")
    axes[0].set_ylabel("Aer estimated P(1), Wilson 95% interval")
    axes[1].legend(loc="upper left", frameon=False)
    fig.suptitle("Qiskit Aer SWAP-test circuits reproduce the exact statistics", fontsize=14)
    fig.tight_layout()
    figure = figures / "core_validation.png"
    fig.savefig(figure, dpi=200)
    plt.close(fig)
    for mode in styles:
        for kind in ("ancilla", "destructive"):
            group = [r for r in rows if r["mode"] == mode and r["kind"] == kind]
            hits = sum(r["inside"] for r in group)
            print(f"{mode:10s} {kind:11s}: {hits}/{len(group)} ({hits / len(group):.1%})")
    print(f"Total runtime: {perf_counter() - start:.2f} s; F7: {figure}")


if __name__ == "__main__":
    main()
