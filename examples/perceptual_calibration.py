"""Reproduce the perceptual measurements using four public-domain Met artworks.

    python examples/perceptual_calibration.py --images <outside-repo-temp-folder> --output <report.csv>

The folder contains texture.jpg, print.jpg, portrait.jpg, landscape.jpg. Download URLs and public-domain
metadata come from https://collectionapi.metmuseum.org/public/collection/v1/objects/<id>, with IDs below.
Splices use the next artwork in the listed order as donor; all other edit parameters are registry defaults
except the sizes/qualities explicitly listed below. No shot outcomes are sampled in this report.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binom

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import swapprint as sp

ARTWORKS = {"texture": 437658, "print": 45434, "portrait": 436532, "landscape": 436535}
EDITS = [
    ("jpeg95", "jpeg", {"quality": 95}),
    ("jpeg90", "jpeg", {"quality": 90}),
    ("jpeg75", "jpeg", {"quality": 75}),
    ("brightness+2", "brightness", {"delta": 2}),
    ("brightness-2", "brightness", {"delta": -2}),
    ("brightness+5", "brightness", {"delta": 5}),
    ("contrast1.05", "contrast", {"factor": 1.05}),
    ("resize128", "resize_roundtrip", {"size": 128}),
    ("text", "text", {}),
    ("splice48", "splice", {"size": 48}),
    ("copy_move24", "copy_move", {"size": 24}),
    ("copy_move48", "copy_move", {"size": 48}),
    ("patch12", "patch", {"size": 12}),
    ("set_pixel", "set_pixel", {}),
    ("patch6", "patch", {"size": 6}),
]


def image_flag_probability(p1: np.ndarray, shots: int, threshold: float) -> tuple[int, float]:
    """Exact independent-binomial image verdict probability, including the strict F_hat < threshold rule.

    k is the smallest integer count that flags a region. The image probability is
    1 - product_u P[Binomial(shots, p1_u) < k]. Use survival probabilities and log1p to retain tiny tails.
    Enumerating possible counts also avoids a rounded algebraic cutoff at equality boundaries.
    """
    counts = np.arange(shots + 1)
    flagged = np.flatnonzero(np.maximum(0, 1 - 2 * counts / shots) < threshold)
    if not flagged.size:
        return shots + 1, 0.0
    k = int(flagged[0])
    tails = binom.sf(k - 1, shots, p1)
    with np.errstate(divide="ignore"):
        probability = -np.expm1(np.log1p(-tails).sum())
    return k, float(probability) if probability else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    images = {label: sp.load_image(args.images / f"{label}.jpg") for label in ARTWORKS}
    labels = list(images)
    rows = []
    for i, (label, img) in enumerate(images.items()):
        fp = sp.fingerprint(img, "perceptual")
        for edit, name, overrides in EDITS:
            params = dict(overrides)
            donor = ""
            if name == "splice":
                donor = labels[(i + 1) % len(labels)]
                params["donor"] = images[donor]
            other = sp.fingerprint(sp.edits.apply(img, name, **params), "perceptual")
            hamming = (fp.data != other.data).sum(axis=1)
            p1 = (1 - sp.overlaps(fp, other).ravel() ** 2) / 2
            k, probability = image_flag_probability(p1, sp.config.PERCEPTUAL_SHOTS, sp.config.PERCEPTUAL_F_THRESHOLD)
            rows.append(dict(
                image=label, source=f"https://www.metmuseum.org/art/collection/search/{ARTWORKS[label]}",
                edit=edit, category=sp.edits.REGISTRY[name].category,
                params_json=json.dumps({**sp.edits.REGISTRY[name].defaults, **overrides, **({"donor": donor} if donor else {})}),
                flat_sigma=sp.config.PHASH_FLAT_SIGMA, threshold=sp.config.PERCEPTUAL_F_THRESHOLD,
                shots=sp.config.PERCEPTUAL_SHOTS, first_flag_count=k,
                hamming_median=float(np.median(hamming)), hamming_max=int(hamming.max()),
                hamming_json=json.dumps(hamming.tolist()), p1_json=json.dumps(p1.tolist()),
                image_flag_probability=probability,
            ))
    with args.output.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("Cells: median/max Hamming; image flag probability in percent (exact binomial calculation).")
    print("| Edit | Seurat | Hokusai | Portrait | Landscape |")
    print("|---|---|---|---|---|")
    for edit, _, _ in EDITS:
        cells = []
        for label in labels:
            row = next(r for r in rows if r["image"] == label and r["edit"] == edit)
            cells.append(f'{row["hamming_median"]:g}/{row["hamming_max"]}; {100 * row["image_flag_probability"]:.4g}%')
        print(f"| {edit} | " + " | ".join(cells) + " |")
    print(f"\nReport: {args.output}")
    for edit in ["benign", "text", "splice48", "copy_move24", "copy_move48"]:
        rates = [r["image_flag_probability"] for r in rows if (r["category"] == "benign" if edit == "benign" else r["edit"] == edit)]
        print(f"{edit}: mean={np.mean(rates):.12g}, min={min(rates):.12g}, max={max(rates):.12g}")


if __name__ == "__main__":
    main()
