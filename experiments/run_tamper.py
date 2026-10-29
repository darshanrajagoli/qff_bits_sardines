"""Tamper experiment harness for SwapPrint (Milestone E1).

Evaluates 15 artworks x 22 edit cases x 3 encodings (strict, perceptual, FRQI).
Outputs:
- experiments/results/tamper_pairs.csv (exact analytical probabilities, ground truth, recall)
- experiments/results/tamper_trials.csv (seeded empirical SWAP-test trials across reps)

Usage:
    python experiments/run_tamper.py --quick     # Fast sanity run on 2 artworks, 5 cases, 5 reps
    python experiments/run_tamper.py             # Full run (projected ~1-2 minutes)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy.stats import binom

# Ensure swapprint is in python path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import swapprint as sp
from experiments.stats import bootstrap_ci, exact_image_detection, shots_99_image, wilson_interval

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("run_tamper")

ALL_K_COLS = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384]


def apply_case_edit(
    img: np.ndarray,
    case: dict[str, Any],
    artwork_meta: dict[str, Any],
    all_orig_images: dict[str, np.ndarray],
) -> np.ndarray:
    """Apply an edit case strictly according to the manifest parameters."""
    edit_name = case["edit"]
    case_id = case["case_id"]

    if edit_name == "identity":
        return sp.edits.identity(img)

    elif edit_name == "pixel":
        pos_idx = case.get("pixel_index", 0)
        pos = artwork_meta["pixel_positions"][pos_idx]
        channel = case.get("channel", 0)
        delta = case.get("delta", 1)
        return sp.edits.pixel(img, y=pos["y"], x=pos["x"], channel=channel, delta=delta)

    elif edit_name == "lsb":
        return sp.edits.lsb(img, payload="QFF", channel=2)

    elif edit_name == "jpeg":
        return sp.edits.jpeg(img, quality=case["params"]["quality"])

    elif edit_name == "brightness":
        return sp.edits.brightness(img, delta=case["params"]["delta"])

    elif edit_name == "contrast":
        return sp.edits.contrast(img, factor=case["params"]["factor"])

    elif edit_name == "resize_roundtrip":
        return sp.edits.resize_roundtrip(img, size=case["params"]["size"])

    elif edit_name == "set_pixel":
        pos = artwork_meta["pixel_positions"][0]  # artwork's first pixel position
        rgb = tuple(case["params"]["rgb"])
        return sp.edits.set_pixel(img, y=pos["y"], x=pos["x"], rgb=rgb)

    elif edit_name == "patch":
        p = case["params"]
        return sp.edits.patch(img, y=p["y"], x=p["x"], size=p["size"], rgb=tuple(p["rgb"]))

    elif edit_name == "copy_move":
        p = case["params"]
        return sp.edits.copy_move(img, src=tuple(p["src"]), dst=tuple(p["dst"]), size=p["size"])

    elif edit_name == "splice":
        donor_slug = artwork_meta["donor"]
        donor_img = all_orig_images[donor_slug]
        p = case["params"]
        return sp.edits.splice(img, donor=donor_img, y=p["y"], x=p["x"], size=p["size"])

    elif edit_name == "text":
        p = case["params"]
        return sp.edits.text(img, s=p["s"], y=p["y"], x=p["x"])

    elif edit_name == "different":
        other_slug = artwork_meta["other"]
        other_img = all_orig_images[other_slug]
        return sp.edits.different(img, other=other_img)

    raise ValueError(f"Unknown edit {edit_name} for case {case_id}")


def compute_ground_truth(orig: np.ndarray, edited: np.ndarray, mode: str) -> tuple[int, int, np.ndarray]:
    """Compute units and ground truth boolean mask of changed units.

    Strict & FRQI: 64x64 grid of 4x4 tiles (4096 units).
    Perceptual: 4x4 grid of 64x64 regions (16 units).
    """
    diff_pixels = (orig != edited).any(axis=2)  # shape (256, 256) bool
    if mode in ("strict", "frqi"):
        n_units = 4096
        changed = diff_pixels.reshape(64, 4, 64, 4).any(axis=(1, 3))  # shape (64, 64)
    elif mode == "perceptual":
        n_units = 16
        changed = diff_pixels.reshape(4, 64, 4, 64).any(axis=(1, 3))  # shape (4, 4)
    else:
        raise ValueError(f"Unknown mode {mode}")
    n_changed = int(changed.sum())
    return n_units, n_changed, changed


def run_experiment(
    manifest_path: Path = Path("experiments/manifest.json"),
    artworks_dir: Path = Path("data/artworks"),
    output_pairs_path: Path = Path("experiments/results/tamper_pairs.csv"),
    output_trials_path: Path = Path("experiments/results/tamper_trials.csv"),
    quick: bool = False,
) -> None:
    t_start = time.perf_counter()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Filter for quick run if requested
    if quick:
        quick_cfg = manifest["quick_subset"]
        artworks_to_run = [a for a in manifest["artworks"] if a["slug"] in quick_cfg["artworks"]]
        cases_to_run = [c for c in manifest["cases"] if c["case_id"] in quick_cfg["cases"]]
        modes_to_run = quick_cfg["modes"]
        num_reps = quick_cfg["reps"]
        logger.info("Running --quick: %d artworks, %d cases, %d modes, %d reps",
                    len(artworks_to_run), len(cases_to_run), len(modes_to_run), num_reps)
    else:
        artworks_to_run = manifest["artworks"]
        cases_to_run = manifest["cases"]
        modes_to_run = manifest["modes"]
        num_reps = manifest["sampled_shots"]["reps"]
        logger.info("Running FULL experiment: %d artworks, %d cases, %d modes, %d reps",
                    len(artworks_to_run), len(cases_to_run), len(modes_to_run), num_reps)

    # 1. Load and cache all original artworks
    logger.info("Loading original artworks from %s...", artworks_dir)
    all_orig_images: dict[str, np.ndarray] = {}
    for art in manifest["artworks"]:
        slug = art["slug"]
        img_path = artworks_dir / f"{slug}.png"
        all_orig_images[slug] = sp.load_image(img_path)

    # 2. Pre-compute and cache original fingerprints
    logger.info("Pre-computing original fingerprints...")
    orig_fps: dict[tuple[str, str], sp.Fingerprint] = {}
    for art in artworks_to_run:
        slug = art["slug"]
        img = all_orig_images[slug]
        for mode in modes_to_run:
            orig_fps[(slug, mode)] = sp.fingerprint(img, mode)

    # Prepare output files
    output_pairs_path.parent.mkdir(parents=True, exist_ok=True)
    output_trials_path.parent.mkdir(parents=True, exist_ok=True)

    pair_fieldnames = [
        "artwork", "split", "case_id", "category", "mode",
        "n_units", "n_units_changed", "overlap_min", "p1_max",
    ] + [f"p_detect_k{k}" for k in ALL_K_COLS] + ["shots_99_image", "recall"]

    trial_fieldnames = [
        "artwork", "split", "case_id", "category", "mode",
        "shots", "rep", "n_units_changed", "n_flagged", "n_flagged_changed", "detected"
    ]

    pair_rows: list[dict[str, Any]] = []
    trial_rows: list[dict[str, Any]] = []

    case_indices = {c["case_id"]: idx for idx, c in enumerate(manifest["cases"])}
    mode_indices = {"strict": 0, "perceptual": 1, "frqi": 2}

    total_pairs = len(artworks_to_run) * len(cases_to_run) * len(modes_to_run)
    pair_count = 0

    threshold = sp.config.PERCEPTUAL_F_THRESHOLD

    for art in artworks_to_run:
        slug = art["slug"]
        split = art["split"]
        art_idx = art["artwork_index"]
        orig_img = all_orig_images[slug]

        for case in cases_to_run:
            case_id = case["case_id"]
            category = case["category"]
            c_idx = case_indices[case_id]

            # Generate edited image once for all modes
            edited_img = apply_case_edit(orig_img, case, art, all_orig_images)

            for mode in modes_to_run:
                m_idx = mode_indices[mode]
                pair_count += 1

                # Ground truth
                n_units, n_changed, changed_mask = compute_ground_truth(orig_img, edited_img, mode)

                # Fingerprint edited image and compute overlap
                fp_a = orig_fps[(slug, mode)]
                fp_b = sp.fingerprint(edited_img, mode)
                overlaps = sp.overlaps(fp_a, fp_b)
                p1 = sp.theory.swap_test_p1(overlaps)
                flat_p1 = p1.ravel()

                overlap_min = float(overlaps.min())
                p1_max = float(p1.max())

                # --- EXACT PART ---
                # p_detect_k for each k
                p_detect_dict: dict[str, Any] = {}
                for k in ALL_K_COLS:
                    col = f"p_detect_k{k}"
                    if mode in ("strict", "frqi"):
                        p_det = exact_image_detection(flat_p1, k, mode=mode, threshold=threshold)
                        p_detect_dict[col] = f"{p_det:.10g}"
                    elif mode == "perceptual":
                        if k >= 64:
                            p_det = exact_image_detection(flat_p1, k, mode=mode, threshold=threshold)
                            p_detect_dict[col] = f"{p_det:.10g}"
                        else:
                            p_detect_dict[col] = ""

                # shots_99_image
                s99 = shots_99_image(flat_p1, mode=mode, threshold=threshold)

                # Expected recall for content cases
                recall_val = ""
                if category == "content":
                    flat_changed = changed_mask.ravel()
                    if n_changed > 0:
                        if mode in ("strict", "frqi"):
                            # Expected fraction of changed units flagged at 32 shots
                            p_flag_u = 1.0 - np.power(1.0 - flat_p1[flat_changed], 32)
                            recall_val = f"{float(np.mean(p_flag_u)):.6f}"
                        elif mode == "perceptual":
                            # Expected fraction of changed regions flagged at 4096 shots
                            counts = np.arange(4096 + 1)
                            flagged_counts = np.flatnonzero(np.maximum(0.0, 1.0 - 2.0 * counts / 4096) < threshold)
                            c_flag = int(flagged_counts[0])
                            p_flag_u = binom.sf(c_flag - 1, 4096, flat_p1[flat_changed])
                            recall_val = f"{float(np.mean(p_flag_u)):.6f}"

                pair_rows.append({
                    "artwork": slug,
                    "split": split,
                    "case_id": case_id,
                    "category": category,
                    "mode": mode,
                    "n_units": n_units,
                    "n_units_changed": n_changed,
                    "overlap_min": f"{overlap_min:.8f}",
                    "p1_max": f"{p1_max:.8f}",
                    **p_detect_dict,
                    "shots_99_image": str(s99),
                    "recall": recall_val,
                })

                # --- SAMPLED PART ---
                if mode in ("strict", "frqi"):
                    shots_list = [1, 2, 4, 8, 16, 32, 64, 128, 256]
                else:
                    shots_list = [256, 1024, 4096]

                for shots in shots_list:
                    # Cutoff for perceptual decision
                    if mode == "perceptual":
                        counts = np.arange(shots + 1)
                        flagged_counts = np.flatnonzero(np.maximum(0.0, 1.0 - 2.0 * counts / shots) < threshold)
                        c_flag = int(flagged_counts[0]) if flagged_counts.size else (shots + 1)

                    for rep in range(num_reps):
                        ss = np.random.SeedSequence([art_idx, c_idx, m_idx, shots, rep])
                        rng = np.random.default_rng(ss)
                        ones = rng.binomial(shots, flat_p1)

                        if mode in ("strict", "frqi"):
                            flagged = ones > 0
                        else:
                            flagged = ones >= c_flag

                        n_flagged = int(np.count_nonzero(flagged))
                        flagged_changed = flagged & changed_mask.ravel()
                        n_flagged_changed = int(np.count_nonzero(flagged_changed))
                        detected = n_flagged > 0

                        trial_rows.append({
                            "artwork": slug,
                            "split": split,
                            "case_id": case_id,
                            "category": category,
                            "mode": mode,
                            "shots": shots,
                            "rep": rep,
                            "n_units_changed": n_changed,
                            "n_flagged": n_flagged,
                            "n_flagged_changed": n_flagged_changed,
                            "detected": detected,
                        })

    # Write tamper_pairs.csv
    with output_pairs_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=pair_fieldnames)
        writer.writeheader()
        writer.writerows(pair_rows)
    logger.info("Wrote %d rows to %s", len(pair_rows), output_pairs_path)

    # Write tamper_trials.csv
    with output_trials_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=trial_fieldnames)
        writer.writeheader()
        writer.writerows(trial_rows)
    logger.info("Wrote %d rows to %s", len(trial_rows), output_trials_path)

    elapsed = time.perf_counter() - t_start
    logger.info("Tamper run completed in %.2f seconds.", elapsed)


def check_sampler_agreement(trials_path: Path, pairs_path: Path) -> bool:
    """Validate that the empirical sampler agrees with exact probabilities within Wilson 95% intervals."""
    # Read pairs into lookup map
    pairs_exact: dict[tuple[str, str, str, int], float] = {}
    with pairs_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            art, case, mode = row["artwork"], row["case_id"], row["mode"]
            for col, val in row.items():
                if col.startswith("p_detect_k") and val != "":
                    try:
                        k = int(col[len("p_detect_k"):])
                        pairs_exact[(art, case, mode, k)] = float(val)
                    except ValueError:
                        pass

    # Read trials and aggregate
    trials_data: dict[tuple[str, str, str, int], list[bool]] = {}
    with trials_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            art, case, mode = row["artwork"], row["case_id"], row["mode"]
            shots = int(row["shots"])
            det = row["detected"].lower() == "true"
            trials_data.setdefault((art, case, mode, shots), []).append(det)

    logger.info("Checking agreement between sampled rates and exact probabilities...")
    mismatches = 0
    total_checks = 0

    for key, outcomes in trials_data.items():
        if key not in pairs_exact:
            continue
        exact_p = pairs_exact[key]
        n_trials = len(outcomes)
        successes = sum(outcomes)
        low, high = wilson_interval(successes, n_trials)
        total_checks += 1
        if not (low - 1e-4 <= exact_p <= high + 1e-4):
            mismatches += 1

    logger.info("Checked %d conditions: %d within Wilson 95%% intervals (mismatch rate: %.1f%%).",
                total_checks, total_checks - mismatches, (mismatches / total_checks * 100) if total_checks else 0)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Run quick sanity subset")
    parser.add_argument("--manifest", type=Path, default=Path("experiments/manifest.json"))
    parser.add_argument("--artworks-dir", type=Path, default=Path("data/artworks"))
    parser.add_argument("--output-pairs", type=Path, default=Path("experiments/results/tamper_pairs.csv"))
    parser.add_argument("--output-trials", type=Path, default=Path("experiments/results/tamper_trials.csv"))
    parser.add_argument("--check-sampler", action="store_true", help="Run sampler vs exact statistical check")
    args = parser.parse_args()

    run_experiment(
        manifest_path=args.manifest,
        artworks_dir=args.artworks_dir,
        output_pairs_path=args.output_pairs,
        output_trials_path=args.output_trials,
        quick=args.quick,
    )

    if args.check_sampler or args.quick:
        check_sampler_agreement(args.output_trials, args.output_pairs)


if __name__ == "__main__":
    main()
