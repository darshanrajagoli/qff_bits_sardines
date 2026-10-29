"""Calibrate Perceptual Mode (Milestone E3).

Tunes flat_sigma, threshold t, and shots on the 6 calibration paintings only:
- flat_sigma in [0, 12.5, 25.0, 50.0, 100.0]
- threshold t in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85]
- shots in [1024, 2048, 4096, 8192]

Subject to constraints:
- Mean benign false-alarm <= 1% (0.01) across calibration paintings
- No individual calibration painting benign false-alarm > 5% (0.05)
Objective:
- Maximize mean content detection
- Tie-breaking: fewer shots, then largest margin over the worst benign case.

Evaluates the chosen setting ONCE on the 6 held-out paintings (macro-average + 95% bootstrap CI).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import binom

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import swapprint as sp
from experiments.run_tamper import apply_case_edit
from experiments.stats import bootstrap_ci

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("calibrate_perceptual")

SIGMA_GRID = [0.0, 12.5, 25.0, 50.0, 100.0]
T_GRID = [round(0.30 + i * 0.05, 2) for i in range(12)]  # 0.30 to 0.85
SHOTS_GRID = [1024, 2048, 4096, 8192]


def calc_image_flag_prob(p1: np.ndarray, shots: int, threshold: float) -> float:
    """Exact image-level detection probability for perceptual mode."""
    flat_p1 = np.asarray(p1, dtype=np.float64).ravel()
    counts = np.arange(shots + 1)
    flagged = np.flatnonzero(np.maximum(0.0, 1.0 - 2.0 * counts / shots) < threshold)
    if not flagged.size:
        return 0.0
    c_flag = int(flagged[0])
    p_u = binom.sf(c_flag - 1, shots, flat_p1)
    if np.any(p_u >= 1.0):
        return 1.0
    return float(-np.expm1(np.sum(np.log1p(-p_u))))


def main() -> None:
    manifest_path = Path("experiments/manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artworks_dir = Path("data/artworks")

    # Load all images
    all_orig_images: dict[str, np.ndarray] = {
        art["slug"]: sp.load_image(artworks_dir / f"{art['slug']}.png")
        for art in manifest["artworks"]
    }

    # Group cases into benign and content
    benign_cases = [c for c in manifest["cases"] if c["category"] == "benign"]
    content_cases = [c for c in manifest["cases"] if c["category"] == "content"]

    logger.info("Benign cases (%d): %s", len(benign_cases), [c["case_id"] for c in benign_cases])
    logger.info("Content cases (%d): %s", len(content_cases), [c["case_id"] for c in content_cases])

    # 1. Precompute p1 arrays for all (artwork, case, sigma)
    # p1_cache[(slug, case_id, sigma)] = array of length 16
    p1_cache: dict[tuple[str, str, float], np.ndarray] = {}

    all_cases = benign_cases + content_cases
    all_artworks = manifest["artworks"]

    logger.info("Precomputing perceptual overlaps across %d artworks, %d cases, %d sigmas...",
                len(all_artworks), len(all_cases), len(SIGMA_GRID))

    for art in all_artworks:
        slug = art["slug"]
        orig_img = all_orig_images[slug]

        for sigma in SIGMA_GRID:
            bits_orig = sp.encodings.perceptual(orig_img, flat_sigma=sigma)

            for case in all_cases:
                case_id = case["case_id"]
                edited_img = apply_case_edit(orig_img, case, art, all_orig_images)
                bits_edited = sp.encodings.perceptual(edited_img, flat_sigma=sigma)

                d = (bits_orig != bits_edited).sum(axis=1)  # shape (16,)
                overlap = 1.0 - 2.0 * d / 64.0
                p1 = np.clip((1.0 - np.square(overlap)) / 2.0, 0.0, 0.5)
                p1_cache[(slug, case_id, sigma)] = p1

    # 2. Grid search on calibration artworks
    cal_artworks = [a for a in manifest["artworks"] if a["split"] == "calibration"]
    cal_slugs = [a["slug"] for a in cal_artworks]
    logger.info("Calibration paintings (%d): %s", len(cal_slugs), cal_slugs)

    results_grid: list[dict[str, Any]] = []

    for sigma in SIGMA_GRID:
        for shots in SHOTS_GRID:
            for t in T_GRID:
                # Score per calibration artwork
                art_benign_rates = []
                art_content_rates = []

                for slug in cal_slugs:
                    # Benign image detection
                    b_probs = [
                        calc_image_flag_prob(p1_cache[(slug, c["case_id"], sigma)], shots, t)
                        for c in benign_cases
                    ]
                    art_benign_rates.append(float(np.mean(b_probs)))

                    # Content image detection
                    c_probs = [
                        calc_image_flag_prob(p1_cache[(slug, c["case_id"], sigma)], shots, t)
                        for c in content_cases
                    ]
                    art_content_rates.append(float(np.mean(c_probs)))

                mean_benign = float(np.mean(art_benign_rates))
                max_benign = float(np.max(art_benign_rates))
                mean_content = float(np.mean(art_content_rates))
                min_content = float(np.min(art_content_rates))

                # Feasibility check
                feasible = (mean_benign <= 0.01) and (max_benign <= 0.05)

                results_grid.append({
                    "sigma": sigma,
                    "threshold": t,
                    "shots": shots,
                    "feasible": feasible,
                    "mean_content": mean_content,
                    "min_content": min_content,
                    "mean_benign": mean_benign,
                    "max_benign": max_benign,
                    "art_benign_rates": art_benign_rates,
                    "art_content_rates": art_content_rates,
                })

    feasible_results = [r for r in results_grid if r["feasible"]]
    logger.info("Total grid points: %d, Feasible: %d", len(results_grid), len(feasible_results))

    if not feasible_results:
        logger.warning("No setting satisfied mean_benign <= 1% and max_benign <= 5%!")
        best = min(results_grid, key=lambda r: (r["mean_benign"], -r["mean_content"]))
    else:
        # Sort by:
        # 1. Highest mean_content (descending)
        # 2. Fewer shots (ascending)
        # 3. Largest margin over worst benign (i.e. lowest max_benign)
        feasible_results.sort(key=lambda r: (-r["mean_content"], r["shots"], r["max_benign"]))
        best = feasible_results[0]

    chosen_sigma = best["sigma"]
    chosen_t = best["threshold"]
    chosen_shots = best["shots"]

    print("\n" + "=" * 60)
    print("TOP FEASIBLE CALIBRATION SETTINGS (ranked):")
    print("=" * 60)
    print("Rank | sigma | thresh | shots | mean content | min content | mean benign | max benign")
    print("-" * 75)
    for rank, r in enumerate(feasible_results[:10], 1):
        print(f"{rank:4d} | {r['sigma']:5.1f} | {r['threshold']:6.2f} | {r['shots']:5d} | "
              f"{100*r['mean_content']:11.2f}% | {100*r['min_content']:10.2f}% | "
              f"{100*r['mean_benign']:10.2f}% | {100*r['max_benign']:9.2f}%")

    print("\n" + "=" * 60)
    print(f"CHOSEN OPTIMAL SETTING: sigma={chosen_sigma}, threshold={chosen_t}, shots={chosen_shots}")
    print(f"Calibration performance: Content={100*best['mean_content']:.2f}% (min={100*best['min_content']:.2f}%), "
          f"Benign FA={100*best['mean_benign']:.2f}% (max={100*best['max_benign']:.2f}%)")
    print("=" * 60 + "\n")

    # 3. Evaluate ONCE on Held-out split (resampling artworks for 95% bootstrap CI)
    heldout_artworks = [a for a in manifest["artworks"] if a["split"] == "heldout"]
    heldout_slugs = [a["slug"] for a in heldout_artworks]
    logger.info("Held-out paintings (%d): %s", len(heldout_slugs), heldout_slugs)

    heldout_benign_per_art = []
    heldout_content_per_art = []
    heldout_case_rates: dict[str, list[float]] = {}

    for slug in heldout_slugs:
        b_probs = []
        for c in benign_cases:
            p = calc_image_flag_prob(p1_cache[(slug, c["case_id"], chosen_sigma)], chosen_shots, chosen_t)
            b_probs.append(p)
            heldout_case_rates.setdefault(c["case_id"], []).append(p)
        heldout_benign_per_art.append(float(np.mean(b_probs)))

        c_probs = []
        for c in content_cases:
            p = calc_image_flag_prob(p1_cache[(slug, c["case_id"], chosen_sigma)], chosen_shots, chosen_t)
            c_probs.append(p)
            heldout_case_rates.setdefault(c["case_id"], []).append(p)
        heldout_content_per_art.append(float(np.mean(c_probs)))

    mean_h_benign, low_h_benign, high_h_benign = bootstrap_ci(heldout_benign_per_art, seed=42)
    mean_h_content, low_h_content, high_h_content = bootstrap_ci(heldout_content_per_art, seed=42)

    print("HELD-OUT EVALUATION (once, frozen setting):")
    print(f"Content Detection: {100*mean_h_content:.2f}% [95% CI: {100*low_h_content:.2f}%, {100*high_h_content:.2f}%]")
    print(f"Benign False-Alarm: {100*mean_h_benign:.2f}% [95% CI: {100*low_h_benign:.2f}%, {100*high_h_benign:.2f}%]")
    print("\nHeld-out per-case mean detection:")
    for c in all_cases:
        cid = c["case_id"]
        rates = heldout_case_rates[cid]
        print(f"  {cid:14s} ({c['category']:10s}): {100*np.mean(rates):6.2f}%")

    # 4. Stress split (evaluated separately)
    stress_artworks = [a for a in manifest["artworks"] if a["split"] == "stress"]
    stress_slugs = [a["slug"] for a in stress_artworks]
    print("\nSTRESS IMAGES (reported separately):")
    for slug in stress_slugs:
        b_probs = [calc_image_flag_prob(p1_cache[(slug, c["case_id"], chosen_sigma)], chosen_shots, chosen_t) for c in benign_cases]
        c_probs = [calc_image_flag_prob(p1_cache[(slug, c["case_id"], chosen_sigma)], chosen_shots, chosen_t) for c in content_cases]
        print(f"  {slug:10s}: Content={100*np.mean(c_probs):.2f}%, Benign FA={100*np.mean(b_probs):.2f}%")

    # Save complete report
    out_json = Path("experiments/results/perceptual_calibration.json")
    out_json.write_text(json.dumps({
        "chosen": {
            "flat_sigma": chosen_sigma,
            "threshold": chosen_t,
            "shots": chosen_shots,
        },
        "calibration": {
            "mean_content": best["mean_content"],
            "min_content": best["min_content"],
            "mean_benign": best["mean_benign"],
            "max_benign": best["max_benign"],
            "artworks": cal_slugs,
        },
        "heldout": {
            "mean_content": mean_h_content,
            "ci_content_95": [low_h_content, high_h_content],
            "mean_benign": mean_h_benign,
            "ci_benign_95": [low_h_benign, high_h_benign],
            "artworks": heldout_slugs,
            "per_case_mean": {cid: float(np.mean(rates)) for cid, rates in heldout_case_rates.items()},
        },
    }, indent=2), encoding="utf-8")
    logger.info("Saved %s", out_json)


if __name__ == "__main__":
    main()
