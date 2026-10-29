"""Generate and freeze experiments/manifest.json for the SwapPrint tampering experiment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

ARTWORKS = [
    # Calibration split (6)
    {"slug": "hokusai_great_wave", "split": "calibration"},
    {"slug": "vangogh_straw_hat", "split": "calibration"},
    {"slug": "vangogh_wheat_field", "split": "calibration"},
    {"slug": "seurat_grande_jatte", "split": "calibration"},
    {"slug": "hiroshige_plum_tree", "split": "calibration"},
    {"slug": "rembrandt_self_portrait", "split": "calibration"},
    # Held-out split (6)
    {"slug": "vangogh_bedroom", "split": "heldout"},
    {"slug": "monet_water_lilies", "split": "heldout"},
    {"slug": "caillebotte_paris_street", "split": "heldout"},
    {"slug": "hiroshige_sudden_shower", "split": "heldout"},
    {"slug": "vermeer_water_pitcher", "split": "heldout"},
    {"slug": "turner_venice", "split": "heldout"},
    # Stress split (3)
    {"slug": "synthetic", "split": "stress"},
    {"slug": "flat", "split": "stress"},
    {"slug": "noise", "split": "stress"},
]


def build_manifest() -> dict[str, Any]:
    # Determine cyclic donor/other per split (alphabetical order)
    split_artworks: dict[str, list[str]] = {}
    for art in ARTWORKS:
        split_artworks.setdefault(art["split"], []).append(art["slug"])

    cyclic_partner: dict[str, str] = {}
    for split_name, slugs in split_artworks.items():
        sorted_slugs = sorted(slugs)
        n = len(sorted_slugs)
        for i, s in enumerate(sorted_slugs):
            cyclic_partner[s] = sorted_slugs[(i + 1) % n]

    artworks_meta: list[dict[str, Any]] = []
    for idx, art in enumerate(ARTWORKS):
        slug = art["slug"]
        split = art["split"]
        rng = np.random.default_rng(1000 + idx)
        # 5 distinct or sequential pixel positions
        ys = rng.integers(0, 256, size=5).tolist()
        xs = rng.integers(0, 256, size=5).tolist()
        positions = [{"y": int(y), "x": int(x)} for y, x in zip(ys, xs)]

        artworks_meta.append({
            "artwork_index": idx,
            "slug": slug,
            "split": split,
            "donor": cyclic_partner[slug],
            "other": cyclic_partner[slug],
            "pixel_positions": positions,
        })

    # Build cases specification (22 cases)
    # 1 control, 6 imperceptible, 6 benign, 8 content, 1 different
    cases: list[dict[str, Any]] = [
        {
            "case_id": "identity",
            "category": "control",
            "edit": "identity",
            "params": {},
        },
    ]

    # pixel_1 ... pixel_5
    for i in range(1, 6):
        cases.append({
            "case_id": f"pixel_{i}",
            "category": "imperceptible",
            "edit": "pixel",
            "pixel_index": i - 1,  # 0-based index into pixel_positions
            "channel": i % 3,
            "delta": 1,
            "params": {"channel": i % 3, "delta": 1},
        })

    cases.extend([
        {
            "case_id": "lsb",
            "category": "imperceptible",
            "edit": "lsb",
            "params": {"payload": "QFF", "channel": 2},
        },
        {
            "case_id": "jpeg95",
            "category": "benign",
            "edit": "jpeg",
            "params": {"quality": 95},
        },
        {
            "case_id": "jpeg75",
            "category": "benign",
            "edit": "jpeg",
            "params": {"quality": 75},
        },
        {
            "case_id": "bright_p1",
            "category": "benign",
            "edit": "brightness",
            "params": {"delta": 1},
        },
        {
            "case_id": "bright_p5",
            "category": "benign",
            "edit": "brightness",
            "params": {"delta": 5},
        },
        {
            "case_id": "contrast105",
            "category": "benign",
            "edit": "contrast",
            "params": {"factor": 1.05},
        },
        {
            "case_id": "resize128",
            "category": "benign",
            "edit": "resize_roundtrip",
            "params": {"size": 128},
        },
        {
            "case_id": "set_pixel",
            "category": "content",
            "edit": "set_pixel",
            "pixel_index": 0,  # artwork's first pixel position
            "params": {"rgb": [255, 0, 0]},
        },
        {
            "case_id": "patch2",
            "category": "content",
            "edit": "patch",
            "params": {"y": 100, "x": 100, "size": 2, "rgb": [255, 0, 0]},
        },
        {
            "case_id": "patch6",
            "category": "content",
            "edit": "patch",
            "params": {"y": 100, "x": 100, "size": 6, "rgb": [255, 0, 0]},
        },
        {
            "case_id": "patch12",
            "category": "content",
            "edit": "patch",
            "params": {"y": 100, "x": 100, "size": 12, "rgb": [255, 0, 0]},
        },
        {
            "case_id": "copy_move24",
            "category": "content",
            "edit": "copy_move",
            "params": {"src": [20, 20], "dst": [150, 150], "size": 24},
        },
        {
            "case_id": "copy_move48",
            "category": "content",
            "edit": "copy_move",
            "params": {"src": [20, 20], "dst": [150, 150], "size": 48},
        },
        {
            "case_id": "splice48",
            "category": "content",
            "edit": "splice",
            "params": {"y": 64, "x": 64, "size": 48, "donor": "<cyclic_donor>"},
        },
        {
            "case_id": "text",
            "category": "content",
            "edit": "text",
            "params": {"s": "FAKE", "y": 200, "x": 10},
        },
        {
            "case_id": "different",
            "category": "different",
            "edit": "different",
            "params": {"other": "<cyclic_other>"},
        },
    ])

    manifest = {
        "version": "1.0",
        "description": "Frozen experimental design for SwapPrint tampering experiment (E1)",
        "splits": {
            "calibration": [a["slug"] for a in ARTWORKS if a["split"] == "calibration"],
            "heldout": [a["slug"] for a in ARTWORKS if a["split"] == "heldout"],
            "stress": [a["slug"] for a in ARTWORKS if a["split"] == "stress"],
        },
        "artworks": artworks_meta,
        "cases": cases,
        "modes": ["strict", "perceptual", "frqi"],
        "exact_k_grids": {
            "strict_frqi": [1, 2, 4, 8, 16, 32, 64, 128, 256],
            "perceptual": [64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384],
        },
        "sampled_shots": {
            "strict_frqi": [1, 2, 4, 8, 16, 32, 64, 128, 256],
            "perceptual": [256, 1024, 4096],
            "reps": 50,
        },
        "quick_subset": {
            "artworks": ["synthetic", "hokusai_great_wave"],
            "cases": ["identity", "pixel_1", "jpeg75", "patch12", "splice48"],
            "modes": ["strict", "perceptual", "frqi"],
            "reps": 5,
        },
    }
    return manifest


def main() -> None:
    manifest = build_manifest()
    out_path = Path("experiments/manifest.json")
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote frozen manifest to {out_path} with {len(manifest['artworks'])} artworks and {len(manifest['cases'])} cases.")


if __name__ == "__main__":
    main()
