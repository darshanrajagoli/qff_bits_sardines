"""Reproduce E3 with dead-zone floors; freeze on calibration artworks, then evaluate.

Run from the repository root: .venv/Scripts/python experiments/core_perceptual_v3.py
All flag probabilities are exact binomial tails. Only the E3 uncertainty calculation
resamples (2000 artwork bootstrap replicates, seed 42). Supplemental synthetic seeds
0..15 and JPEG90 are evaluation-only and never enter selection.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import swapprint as sp
from experiments.calibrate_perceptual import SHOTS_GRID, T_GRID, calc_image_flag_prob
from experiments.run_tamper import apply_case_edit
from experiments.stats import bootstrap_ci

FLOOR_GRID = [5.0, 8.0, 10.0, 12.0, 15.0, 20.0]
BASELINE = {"rule": "median", "flat_sigma": 25.0, "threshold": 0.65, "shots": 2048}


def distances(img, edited, **kwargs):
    return (sp.encodings.perceptual(img, **kwargs) !=
            sp.encodings.perceptual(edited, **kwargs)).sum(axis=1)


def probabilities(d, shots, threshold):
    """Vectorized E3 calculation, retaining its reductions and floating-point rule."""
    overlap = 1.0 - 2.0 * d / 64.0
    p1 = np.clip((1.0 - np.square(overlap)) / 2.0, 0.0, 0.5)
    counts = np.arange(shots + 1)
    c_flag = int(np.flatnonzero(np.maximum(0.0, 1.0 - 2.0 * counts / shots) < threshold)[0])
    p_u = binom.sf(c_flag - 1, shots, p1)
    with np.errstate(divide="ignore"):
        return -np.expm1(np.sum(np.log1p(-p_u), axis=-1))


def select(cal_distances, benign_indices, content_indices):
    """Exactly E3's loop order, feasibility, objective, tie-breaks and fallback."""
    rows = []
    for floor, d in zip(FLOOR_GRID, cal_distances):
        for shots in SHOTS_GRID:
            for t in T_GRID:
                p = probabilities(d, shots, t)
                b = p[:, benign_indices].mean(axis=1)
                c = p[:, content_indices].mean(axis=1)
                rows.append(dict(ac_floor=floor, threshold=t, shots=shots,
                                 feasible=bool(b.mean() <= .01 and b.max() <= .05),
                                 mean_content=float(c.mean()), min_content=float(c.min()),
                                 mean_benign=float(b.mean()), max_benign=float(b.max())))
    feasible = [r for r in rows if r["feasible"]]
    best = (sorted(feasible, key=lambda r: (-r["mean_content"], r["shots"], r["max_benign"]))[0]
            if feasible else min(rows, key=lambda r: (r["mean_benign"], -r["mean_content"])))
    return best, rows


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    manifest = json.loads((ROOT / "experiments/manifest.json").read_text(encoding="utf-8"))
    cases = [c for c in manifest["cases"] if c["category"] in ("benign", "content")]
    bi = [i for i, c in enumerate(cases) if c["category"] == "benign"]
    ci = [i for i, c in enumerate(cases) if c["category"] == "content"]
    images = {a["slug"]: sp.load_image(ROOT / "data/artworks" / f"{a['slug']}.png")
              for a in manifest["artworks"]}
    cal = [a for a in manifest["artworks"] if a["split"] == "calibration"]
    # No held-out or stress images are hashed until after the setting is frozen.
    cal_d = []
    for floor in FLOOR_GRID:
        print(f"Calibration AC floor {floor:g}", flush=True)
        cal_d.append(np.array([[distances(images[a["slug"]], apply_case_edit(images[a["slug"]], c, a, images),
                                         rule="deadzone", ac_floor=floor) for c in cases] for a in cal]))
    best, grid = select(cal_d, bi, ci)
    chosen = {"rule": "deadzone", **{k: best[k] for k in ("ac_floor", "threshold", "shots")}}
    print("FROZEN:", chosen, flush=True)
    models = {"v0.2": BASELINE, "v0.3": chosen}
    report = dict(chosen=chosen, calibration=best, calibration_artworks=[a["slug"] for a in cal],
                  grid_points=len(grid), feasible_points=sum(r["feasible"] for r in grid),
                  uncertainty="2000 artwork bootstrap resamples, percentile 95% CI, seed 42 (E3)",
                  heldout={}, stress={}, synthetic16={}, bit_cut={})
    records = [{"record_type": "calibration_grid", **r} for r in grid]
    pairs = []
    jpeg90 = {"case_id": "jpeg90", "category": "benign", "edit": "jpeg", "params": {"quality": 90}}
    eval_cases = cases + [jpeg90]
    for model, settings in models.items():
        shots, t = settings["shots"], settings["threshold"]
        kwargs = {k: v for k, v in settings.items() if k not in ("shots", "threshold")}
        for art in manifest["artworks"]:
            for case in eval_cases:
                img = images[art["slug"]]
                d = distances(img, apply_case_edit(img, case, art, images), **kwargs)
                p = float(probabilities(d, shots, t))
                # Check equivalence to E3's original scalar function on every evaluated pair.
                p1 = np.clip((1 - (1 - 2 * d / 64)**2) / 2, 0, .5)
                assert p == calc_image_flag_prob(p1, shots, t)
                pairs.append(dict(model=model, group=art["split"], artwork=art["slug"],
                                  case_id=case["case_id"], category=case["category"],
                                  probability=p, max_bits=int(d.max())))
        heldout = [a["slug"] for a in manifest["artworks"] if a["split"] == "heldout"]
        report["heldout"][model] = {"artworks": heldout}
        for category in ("benign", "content"):
            rates = [float(np.mean([r["probability"] for r in pairs if r["model"] == model
                                   and r["artwork"] == slug and r["category"] == category
                                   and r["case_id"] != "jpeg90"])) for slug in heldout]
            mean, low, high = bootstrap_ci(rates, seed=42)
            report["heldout"][model][category] = dict(mean=mean, ci95=[low, high], per_artwork=rates)
            records.append(dict(record_type="heldout_summary", model=model, category=category,
                                probability=mean, ci_low=low, ci_high=high))
        for art in [a for a in manifest["artworks"] if a["split"] == "stress"]:
            rr = [r for r in pairs if r["model"] == model and r["artwork"] == art["slug"]]
            report["stress"].setdefault(model, {})[art["slug"]] = {
                **{cat: float(np.mean([r["probability"] for r in rr if r["category"] == cat
                                      and r["case_id"] != "jpeg90"])) for cat in ("benign", "content")},
                "jpeg90": next(r["probability"] for r in rr if r["case_id"] == "jpeg90")}
        synth = {f"seed{s}": sp.synthetic.artwork(s) for s in range(16)}
        names = list(synth)
        for i, slug in enumerate(names):
            # Same case parameters; donors cycle within this evaluation-only set.
            meta = {"donor": names[(i + 1) % 16], "pixel_positions": [{"y": 128, "x": 128}]}
            for case in eval_cases:
                d = distances(synth[slug], apply_case_edit(synth[slug], case, meta, synth), **kwargs)
                pairs.append(dict(model=model, group="synthetic16", artwork=slug, case_id=case["case_id"],
                                  category=case["category"], probability=float(probabilities(d, shots, t)),
                                  max_bits=int(d.max())))
        rr = [r for r in pairs if r["model"] == model and r["group"] == "synthetic16"]
        report["synthetic16"][model] = {
            **{cat: float(np.mean([r["probability"] for r in rr if r["category"] == cat
                                  and r["case_id"] != "jpeg90"])) for cat in ("benign", "content")},
            "jpeg90_mean": float(np.mean([r["probability"] for r in rr if r["case_id"] == "jpeg90"])),
            "jpeg90_above_5pct": sum(r["probability"] > .05 for r in rr if r["case_id"] == "jpeg90")}
        cut = int(np.flatnonzero(np.maximum(0, 1 - 2 * np.arange(shots + 1) / shots) < t)[0])
        d = np.arange(65)
        region_p = probabilities(d[:, None], shots, t)
        ideal = d[(1 - 2 * d / 64)**2 < t]
        report["bit_cut"][model] = dict(c_flag=cut, ideal_distance_interval=[int(ideal[0]), int(ideal[-1])],
                                               region_probabilities=region_p.tolist())
    out = ROOT / "experiments/results"
    figdir = ROOT / "experiments/figures"
    out.mkdir(exist_ok=True)
    figdir.mkdir(exist_ok=True)
    records.extend({"record_type": "evaluation_pair", **r} for r in pairs)
    write_csv(out / "core_perceptual_v3.csv", records)
    (out / "core_perceptual_v3.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # One row per evaluated image/case: full-precision source data for both panels.
    write_csv(figdir / "core_perceptual_ablation_data.csv", pairs)
    make_figure(pairs, cases, chosen, figdir)
    print(json.dumps(report, indent=2))


def make_figure(pairs, cases, chosen, figdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    if (ROOT / "swapprint/style.py").exists():
        from swapprint import style
        style.use()
    models = ["v0.2", "v0.3"]
    model_labels = {"v0.2": "v0.2 median (default)", "v0.3": "Dead-zone (ablation)"}
    colors = ["#0072B2", "#D55E00"]
    labels = [c["case_id"] for c in cases]
    fig, (ax, heat) = plt.subplots(1, 2, figsize=(16, 7.5), layout="none",
                                  gridspec_kw={"width_ratios": [1, 1.65]})
    for j, model in enumerate(models):
        values = [np.mean([r["probability"] for r in pairs if r["model"] == model
                           and r["group"] == "heldout" and r["case_id"] == cid]) for cid in labels]
        ax.barh(np.arange(len(labels)) + (j - .5) * .36, np.array(values) * 100, .34,
                color=colors[j], label=model_labels[model])
    ax.set(yticks=np.arange(len(labels)), yticklabels=labels, xlim=(0, 103),
           xlabel="Image flag probability (%)", title="(a) Six held-out paintings · mean per case")
    ax.invert_yaxis()
    ax.grid(False, axis="y")
    ax.axhline(5.5, color=".7", linewidth=.8)
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    columns = labels + ["jpeg90"]
    groups = ["synthetic16", "synthetic", "flat", "noise"]
    values = []
    rowlabels = []
    for group in groups:
        for model in models:
            values.append([100 * np.mean([r["probability"] for r in pairs if r["model"] == model
                                          and (r["group"] == group if group == "synthetic16" else r["artwork"] == group)
                                          and r["case_id"] == cid]) for cid in columns])
            rowlabels.append(f"{'16 synthetic seeds' if group == 'synthetic16' else group} · "
                             f"{'median' if model == 'v0.2' else 'dead-zone'}")
    im = heat.imshow(values, cmap="cividis", vmin=0, vmax=100, aspect="auto")
    heat.grid(False)
    heat.set(xticks=np.arange(len(columns)), xticklabels=columns,
             yticks=np.arange(len(rowlabels)), yticklabels=rowlabels,
             title="(b) Evaluation-only synthetics and stress images")
    plt.setp(heat.get_xticklabels(), rotation=60, ha="right", rotation_mode="anchor")
    for y in [1.5, 3.5, 5.5]:
        heat.axhline(y, color="white", linewidth=2)
    heat.axvline(5.5, color="white", linewidth=1)
    heat.axvline(13.5, color="white", linewidth=1)
    fig.colorbar(im, ax=heat, label="Image flag probability (%)", fraction=.035, pad=.025)
    fig.suptitle(f"Keep v0.2 median as default: median + flat (t=0.65, k=2048) vs "
                 f"dead-zone {chosen['ac_floor']:g} (t={chosen['threshold']}, k={chosen['shots']})")
    fig.tight_layout(rect=(0, 0, 1, .95))
    fig.savefig(figdir / "core_perceptual_ablation.png", dpi=200, facecolor="white")
    plt.close(fig)
    path = figdir / "core_captions.json"
    captions = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    captions["core_perceptual_ablation.png"] = (
        f"Default v0.2 median + AC RMS cutoff 25 (t=0.65, 2048 shots) versus ablation AC > {chosen['ac_floor']:g} "
        f"(t={chosen['threshold']}, {chosen['shots']} shots), selected using exactly E3's six calibration artworks, "
        "cases, constraints and tie-breaks. Panel (a) averages exact image flag probabilities over six held-out "
        "paintings, with benign cases above the divider and all eight content cases below (including tiny edits). "
        "Panel (b) reports the same cases and supplemental JPEG90 for synthetic seeds 0..15 (mean; cyclic donors), "
        "and each manifest stress image separately. Every cell uses exact binomial tails and the probability "
        "of any region flagging; no measurement sampling. Neither supplemental synthetics nor JPEG90 enters selection. "
        "Full-precision per-image data: core_perceptual_ablation_data.csv; artwork bootstrap intervals: "
        "../results/core_perceptual_v3.json. The dead-zone removes the flat-region cliff: synthetic stress "
        "benign false alarm 37.78% to 0.157%; mean JPEG 90 false alarm over 16 synthetic seeds 62.93% to 0.059%. "
        "But held-out benign false alarm rises from 2.78% [95% CI 0.00%, 8.33%] to 14.09% [5.84%, 22.37%], "
        "while content detection rises from 65.14% [59.45%, 70.83%] to 72.95% [66.74%, 79.18%]. "
        "This did not generalise, so v0.2 remains the default; dead-zone is an ablation only. "
        "Historical E3 outputs are unchanged.")
    path.write_text(json.dumps(captions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
