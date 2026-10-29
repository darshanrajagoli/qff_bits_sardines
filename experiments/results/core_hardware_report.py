"""Rebuild F8, its data/caption, C3 docs and five-line summary from saved results.

No service calls or hardware submissions. Run with the repo .venv Python.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "experiments/results"
FIGURES = ROOT / "experiments/figures"


def write_csv(path, rows):
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, columns)
        writer.writeheader()
        writer.writerows(rows)


def report():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from swapprint import style
    style.use("white")

    source = RESULTS / "core_hardware.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = data["circuits"]
    with (RESULTS / "core_noise.csv").open(encoding="utf-8") as f:
        noise = [dict(r, q=int(r["q"]), transpile_seed=int(r["transpile_seed"]), shots=int(r["shots"]),
                      **{k: float(r[k]) for k in ("p1_raw", "p1_raw_lo", "p1_raw_hi", "p1_cal", "p1_cal_lo", "p1_cal_hi")})
                 for r in csv.DictReader(f) if r["backend"] == "aer-noisy:FakeFez"]
    # The stored C2 study used the same fixed toy-state seed, 2026.
    noise_meta = json.loads((RESULTS / "core_noise_run.json").read_text(encoding="utf-8"))
    assert noise_meta["state_seed"] == 2026 == rows[0]["seed"]
    keys = list(dict.fromkeys((r["q"], r["pair"], r["family"]) for r in rows))
    plotted = []
    fig, axes = plt.subplots(2, 2, figsize=(15.8, 9.0), layout="none",
                             gridspec_kw=dict(width_ratios=[3.9, 1.3]))
    handles = {}

    def point(ax, x, y, lo, hi, series, color, marker, filled=True):
        # Percentile bootstrap intervals can exclude a clipped point estimate.
        # Draw their endpoints directly rather than force them to bracket it.
        ax.vlines(x, lo, hi, color=color, linewidth=1.35)
        ax.hlines([lo, hi], x-.025, x+.025, color=color, linewidth=1.1)
        h, = ax.plot(x, y, marker, color=color, markerfacecolor=color if filled else "white",
                     markersize=5.4, markeredgewidth=1.25, linestyle="none", label=series)
        handles.setdefault(series, h)

    for row_index, kind in enumerate(("ancilla", "destructive")):
        ax, zoom = axes[row_index]
        selected = [r for r in rows if r["kind"] == kind]
        for r in selected:
            key = (r["q"], r["pair"], r["family"])
            x = keys.index(key)
            comparisons = [n for n in noise if (n["q"], n["pair"], n["family"], n["kind"]) == (*key, kind)]
            assert len(comparisons) == 3
            targets = [(ax, x)] + ([(zoom, r["q"]-1)] if r["pair"] == "same" else [])
            for metric, offset, marker, filled, label in (
                ("raw", -.13, "o", False, "Hardware raw"),
                ("cal", 0, "D", True, "Hardware readout-corrected")):
                plotted.append(dict(device=r["device"], source="hardware", series=metric,
                                    q=r["q"], pair=r["pair"], family=r["family"], kind=kind,
                                    shots=r["shots"], transpile_seed=r["transpile_seed"],
                                    p1=r[f"p1_{metric}"], lo=r[f"p1_{metric}_lo"], hi=r[f"p1_{metric}_hi"],
                                    job_id=r["job_id"]))
                for target, xx in targets:
                    point(target, xx+offset, r[f"p1_{metric}"], r[f"p1_{metric}_lo"],
                          r[f"p1_{metric}_hi"], label, "#8a3ffc", marker, filled)
            for index, n in enumerate(sorted(comparisons, key=lambda n: n["transpile_seed"])):
                plotted.append(dict(device="FakeFez", source="simulation", series="raw",
                                    q=r["q"], pair=r["pair"], family=r["family"], kind=kind,
                                    shots=n["shots"], transpile_seed=n["transpile_seed"],
                                    p1=n["p1_raw"], lo=n["p1_raw_lo"], hi=n["p1_raw_hi"], job_id=""))
                for target, xx in targets:
                    point(target, xx+.15+.045*index, n["p1_raw"], n["p1_raw_lo"], n["p1_raw_hi"],
                          "FakeFez raw (3 routing seeds)", "#0072c3", "s", False)
            plotted.append(dict(device="ideal", source="ideal", series="ideal", q=r["q"], pair=r["pair"],
                                family=r["family"], kind=kind, shots="", transpile_seed="",
                                p1=r["p1_ideal"], lo="", hi="", job_id=""))
            for target, xx in targets:
                h, = target.plot(xx+.38, r["p1_ideal"], "_", color="#161616", markersize=10,
                                  markeredgewidth=1.8, label="Ideal")
                handles.setdefault("Ideal", h)
        ax.set_title(f"{'a' if row_index == 0 else 'b'}   {kind.capitalize()} SWAP test", loc="left", pad=12)
        ax.set_xticks(range(len(keys)), [f"q={q}\n{pair}" + ("\nH control" if family == "hadamard" else "")
                                        for q, pair, family in keys], fontsize=9)
        ax.set_ylim(-.025, .565)
        ax.set_xlim(-.5, len(keys)-.4)
        ax.set_ylabel("SWAP outcome probability  p₁")
        zoom.set_title("Same pairs · expanded", loc="left", fontsize=11, pad=12)
        zoom.set_xticks([0, 1, 2], ["q=1", "q=2", "q=3"])
        same = [r for r in selected if r["pair"] == "same"]
        nsame = [n for n in noise if n["pair"] == "same" and n["kind"] == kind and n["family"] == "random"]
        upper = max([r["p1_raw_hi"] for r in same] + [r["p1_cal_hi"] for r in same] +
                    [n["p1_raw_hi"] for n in nsame]) * 1.18
        zoom.set_ylim(-upper*.045, upper)
        zoom.set_xlim(-.4, 2.5)
        for target in (ax, zoom):
            target.grid(axis="x", visible=False)
            target.axhline(0, color="#a8a8a8", linewidth=.7, zorder=0)
        ax.axvspan(4.5, 5.5, color="#f4f4f4", zorder=0)
    fig.suptitle(f"F8  |  Toy states on {data['device']}", x=.055, y=.985, ha="left", fontsize=21, weight="semibold")
    fig.text(.055, .942, f"Real IBM Heron r2 processor  ·  {len(rows)} toy comparisons  ·  "
             f"{rows[0]['shots']:,} shots per PUB  ·  95% bootstrap intervals", fontsize=11, color="#525252")
    fig.legend(handles.values(), handles.keys(), loc="upper left", bbox_to_anchor=(.048, .92),
               frameon=False, ncols=4, fontsize=10)
    fig.text(.055, .035, "Random sign states unless marked H control. FakeFez: a different device's stored C2 noise snapshot, routing seeds 7 / 23 / 91.\n"
             "Intervals describe shot and calibration sampling only. Noise breaks one-sided error: a threshold is needed; q=11 remains far beyond today's hardware.",
             fontsize=9.5, color="#525252", linespacing=1.6)
    fig.subplots_adjust(left=.06, right=.985, bottom=.145, top=.82, hspace=.49, wspace=.24)
    fig.savefig(FIGURES / "core_hardware.png", dpi=200, facecolor="white")
    plt.close(fig)
    write_csv(FIGURES / "core_hardware_data.csv", plotted)

    comparisons = []
    for r in rows:
        if r["pair"] != "same":
            continue
        n = next(n for n in noise if n["q"] == r["q"] and n["kind"] == r["kind"] and
                 n["family"] == "random" and n["pair"] == "same" and n["transpile_seed"] == 7)
        comparisons.append(dict(q=r["q"], kind=r["kind"], fake_fez=n))
    data["fake_fez_same_comparison"] = comparisons
    source.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    captions_path = FIGURES / "core_captions.json"
    captions = json.loads(captions_path.read_text(encoding="utf-8"))
    captions["core_noise.png"] = captions["core_noise.png"].replace(
        "no physical IBM Quantum hardware was used.",
        f"F6 is simulation only; F8 separately reports toy states on {data['device']}, a real IBM Heron r2 processor.")
    captions["core_hardware.png"] = (
        f"F8: toy states on {data['device']}, a real IBM Heron r2 processor; job {data['job_id']}, {data['date']}. "
        f"{len(rows)} comparisons at {rows[0]['shots']} shots per PUB, with {data['pub_count']-len(rows)} shared all-0/all-1 "
        "readout-calibration PUBs in the same job. Random sign states (state seed 2026), q=1,2,3; same, near (q>=2), "
        "orthogonal; ancilla and destructive; a q=2 Hadamard orthogonal control. ISA optimization level 3, transpiler seed 7. "
        "Hardware raw and independent-bit readout-corrected p1 have 95% percentile parametric-bootstrap intervals from "
        "2000 joint test/calibration resamples. FakeFez raw predictions and their intervals are the three C2 routing seeds "
        "7,23,91 from core_noise.csv, using the same toy-state seed; FakeFez is a different device and a stored "
        "noise snapshot, so this is an illustrative comparison, not validation of a noise model for Marrakesh. "
        "Ideal ticks and same-pair expanded panels are shown. Intervals condition on this run and "
        "exclude device drift, calibration-model error and routing variability. Noise breaks one-sided error, so a "
        "threshold is needed. Readout correction does not remove gate error. These are toy states; q=11 remains far "
        f"beyond today's hardware. Reported QPU usage: {data['qpu_seconds']} seconds ({data['usage_status']}).")
    captions_path.write_text(json.dumps(captions, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    update_docs(data)
    summary(data)


def interval(row, metric):
    return f"{row['p1_'+metric]:.5f} [{row['p1_'+metric+'_lo']:.5f}, {row['p1_'+metric+'_hi']:.5f}]"


def update_docs(data):
    rows = data["circuits"]
    r = next(r for r in rows if r["q"] == 2 and r["pair"] == "same" and r["kind"] == "ancilla")
    paragraph = (f"F8 reports toy states on {data['device']}, a real IBM Heron r2 processor, on {data['date'][:10]} "
        f"(job `{data['job_id']}`): {len(rows)} toy comparisons at {r['shots']} shots per PUB with "
        f"{data['pub_count']-len(rows)} shared readout-calibration PUBs in one job. "
        f"For the q={r['q']} random same-pair ancilla test, {r['ones']}/{r['shots']} outcomes were one: "
        f"raw p1={interval(r, 'raw')}; readout-corrected p1={interval(r, 'cal')}. "
        f"These are 95% percentile parametric-bootstrap intervals from {r['bootstrap_resamples']} joint "
        f"test/calibration resamples, conditional on this run. Reported QPU usage was {data['qpu_seconds']} seconds. "
        "Noise breaks the one-sided error guarantee; a threshold is needed. Readout correction leaves residual "
        "circuit error. This toy-state run establishes no full-image hardware performance: q = 11 remains far "
        "beyond today's hardware. Sources: `experiments/results/core_hardware.json` and "
        "`experiments/figures/core_hardware.png`.")
    for name in ("THEORY.md", "QA.md", "README_sections.md", "CONTRACT.md"):
        path = ROOT / "docs" / name
        text = path.read_text(encoding="utf-8")
        if name == "THEORY.md":
            text = text.replace("**Our run is a classical simulation**, which computes the overlap exactly. Sampling it adds noise and no power.",
                "**Our image experiment uses classical simulation**, which computes the overlap exactly. Sampling it adds noise and no power. F8 separately tests small toy states on a real IBM QPU.")
            text = text.replace("Noise was simulated in Aer using IBM device noise models FakeFez and FakeBrisbane on toy states with q=1–3. No physical IBM Quantum hardware was used. Full-size hardware performance was not established.",
                "Noise was simulated in Aer using IBM device noise models FakeFez and FakeBrisbane on toy states with q=1–3. " + paragraph)
        elif name == "QA.md":
            text = text.replace("All reported runs are classical simulations; data sources are named below.",
                "Image experiments and F6 use classical simulation; F8 separately measures toy states on a real IBM QPU. Data sources are named below.")
            text = text.replace("and we simulate it classically.",
                "and our full-image experiment is classically simulated. F8 separately measures small toy states on a real IBM QPU.")
            text = text.replace("Noise was simulated in Aer using IBM device noise models FakeFez and FakeBrisbane on toy states with q=1–3. No physical IBM Quantum hardware was used. IBM dispatch raises `NotImplementedError`; full-size hardware performance was not established.", paragraph)
            text = text.replace("Everything is classically simulated.", "The image experiments are classically simulated; F8 separately measures small toy states on a real IBM QPU.")
        elif name == "README_sections.md":
            text = text.replace("No physical IBM Quantum hardware was used.", "F6 is simulation only; F8 separately reports a real QPU toy-state run below.")
            text = text.replace("**Hardware (F8).** No physical IBM Quantum hardware was used; there is no QPU result or hardware figure to report. IBM dispatch raises `NotImplementedError`.", "**Hardware (F8).** " + paragraph)
        else:
            text = text.replace('| `"ibm:<device>"` | unimplemented | dispatch raises `NotImplementedError`; no physical IBM Quantum hardware was used |',
                '| `"ibm:<device>"`, `"ibm:least_busy"` | milestone C3 | toy-only client-side Runtime Sampler, level-3 ISA compilation; `run_batch` combines tests and physical-wire calibrations in one job |')
            text = text.replace("Noise was simulated in Aer using IBM device noise models FakeFez and FakeBrisbane on toy states with q=1–3. No physical IBM Quantum hardware was used.", paragraph)
            old = 'Toy runs (`swapprint/toy.py`): `sp.toy.run(q, pair="same"|"orthogonal"|"near", shots=4000, backend=..., kind=...) -> dict`.'
            new = (old + '\n\nC3 adds `sp.toy.run_batch(specs, backend) -> list[dict]`: each spec is a `toy.run` keyword dict '\
                'without backend; common shots are required, readout calibration defaults on, and 2000 bootstrap resamples '\
                'are the batch default. Pass a FakeFez backend object for offline Runtime local testing. IBM selectors '\
                'load `QiskitRuntimeService()` from the saved default account. Results retain the run fields and add '\
                '`kind`, `job_id`, `device`, UTC `date`, `raw_counts`, `p1_raw`, `p1_cal` (when calibrated), interval '\
                'endpoints and physical-wire/calibration details. `on_submitted(job, manifest)` can persist the job ID '\
                'before waiting; the manifest supports decoding a recovered job. IBM execution uses '\
                '`qiskit_ibm_runtime.executor_sampler.Sampler` in Runtime 0.51; the deprecated top-level SamplerV2 '\
                'is not used. Full-image IBM dispatch remains excluded.')
            if "C3 adds `sp.toy.run_batch" not in text:
                text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")


def summary(data):
    headline = []
    for kind in ("ancilla", "destructive"):
        for q in (1, 2, 3):
            r = next(r for r in data["circuits"] if r["q"] == q and r["kind"] == kind and r["pair"] == "same")
            n = next(c["fake_fez"] for c in data["fake_fez_same_comparison"] if c["q"] == q and c["kind"] == kind)
            headline.append(f"{kind} q={q} (N={r['shots']}) raw/cal {interval(r,'raw')}/{interval(r,'cal')} "
                            f"vs FakeFez seed 7 (N={n['shots']}) {interval(n,'raw')}/{interval(n,'cal')}")
    lines = [f"Device: {data['device']} — a real IBM Heron r2 processor; toy states only.",
             f"Job ID: {data['job_id']}.",
             "Headline p1(same), 95% conditional bootstrap intervals: " + "; ".join(headline) + ".",
             f"QPU seconds used: {data['qpu_seconds']} ({data['usage_status']}); estimated {data['estimated_qpu_seconds']:.2f} before submission.",
             f"Status: DONE C3 — real IBM {data['device']} run, job {data['job_id']}; "
             f"{len(data['circuits'])} toy comparisons (q=1/2/3, both SWAP tests), {data['shots']} shots/PUB, "
             f"same-job readout calibration; {data['qpu_seconds']} QPU seconds. F8, counts, bootstrap intervals "
             "and docs saved. Noise breaks one-sided error; a threshold is needed. q=11 remains far beyond "
             "today's hardware. Please integrate F8 and replace the old no-hardware statement in README/app."]
    (RESULTS / "core_hardware_SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    report()
