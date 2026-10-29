"""C2 / F6: toy states on a simulated IBM device noise model.

Run: $env:PYTHONIOENCODING='utf-8'; .venv/Scripts/python -m experiments.core_noise
Cached real transpilations are reused; --refresh recomputes all measurements/costs.
No remote service or IBM account is used. All uncertainty is conditional shot noise.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

import numpy as np
from scipy.stats import binom

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "experiments" / "results"
FIGURES = ROOT / "experiments" / "figures"
CACHE = RESULTS / "core_noise_cache"
SEEDS = (7, 23, 91)
STATE_SEED = 2026
SHOTS = 4000
RESAMPLES = 2000
LABEL = "toy states on a simulated IBM device noise model"
NOISE_COLUMNS = ("backend q pair family kind transpile_seed shots ones p1_raw p1_raw_lo p1_raw_hi "
                 "p1_cal p1_cal_lo p1_cal_hi p1_ideal two_qubit_gates depth seconds").split()


def write_csv(path, rows, columns=None):
    if not rows:
        return
    columns = columns or list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def exact_threshold(p_same, p_near, max_shots=2_000_000):
    """Smallest k with an integer cutoff c: flag X>c, tau=c/k.

    Enumerate every k (in vectorized blocks); feasibility is not assumed monotone
    because the binomial cutoff is discrete. sf(c,k,p) is the exact tail P(X>c).
    This is a plug-in design, not a confidence guarantee for unknown probabilities.
    """
    if not 0 <= p_same < p_near <= 1:
        return dict(status="no separation", k=None, cutoff=None, tau=None,
                    false_alarm=None, power=None)
    for first in range(1, max_shots + 1, 4096):
        k = np.arange(first, min(first + 4096, max_shots + 1))
        c = binom.ppf(.99, k, p_same).astype(np.int64)
        false_alarm = binom.sf(c, k, p_same)
        power = binom.sf(c, k, p_near)
        good = (false_alarm <= .01) & (power >= .99)
        if good.any():
            j = np.flatnonzero(good)[0]
            return dict(status="ok", k=int(k[j]), cutoff=int(c[j]), tau=float(c[j] / k[j]),
                        false_alarm=float(false_alarm[j]), power=float(power[j]))
    return dict(status=f">{max_shots} shots", k=None, cutoff=None, tau=None,
                false_alarm=None, power=None)


def threshold_table(rows):
    table = []
    fez = [r for r in rows if r["backend"] == "aer-noisy:FakeFez" and r["family"] == "random"]
    for q in sorted({r["q"] for r in fez}):
        for kind in ("ancilla", "destructive"):
            selected = [r for r in fez if r["q"] == q and r["kind"] == kind]
            alternative = "orthogonal" if q == 1 else "near"
            # Guard against observed routing variation, rather than pool layouts.
            p0 = max(r["p1_raw"] for r in selected if r["pair"] == "same")
            p1 = min(r["p1_raw"] for r in selected if r["pair"] == alternative)
            table.append(dict(backend="aer-noisy:FakeFez", q=q, kind=kind,
                              alternative=alternative, p_same=p0, p_near=p1,
                              separation=p1 - p0, probability_source="worst observed raw seed",
                              **exact_threshold(p0, p1)))
    return table


def cost_worker(target, q, output):
    """One bounded subprocess; persist both ISA circuits and their actual costs."""
    from qiskit import qpy, transpile
    from swapprint.circuits import _sign_state_circuit, _swap_prepared
    from swapprint.toy import _toy_codewords

    ca, cb = _toy_codewords(q, "near", "random", STATE_SEED)
    a, b = _sign_state_circuit(ca), _sign_state_circuit(cb)
    circuits = [("preparation", "state", a)] + [
        ("swap", kind, _swap_prepared(a, b, kind)) for kind in ("ancilla", "destructive")]
    kwargs = dict(seed_transpiler=SEEDS[0])
    if target == "FakeFez":
        from qiskit_ibm_runtime.fake_provider import FakeFez
        kwargs.update(backend=FakeFez(), optimization_level=3)
    else:
        kwargs.update(basis_gates=["cx", "rz", "sx", "x"], optimization_level=1)
    rows, compiled = [], []
    for component, kind, qc in circuits:
        start = perf_counter()
        isa = transpile(qc, **kwargs)
        rows.append(dict(target=target, q=q, component=component, kind=kind,
                         family="random", pair="near", state_seed=STATE_SEED,
                         transpile_seed=SEEDS[0], optimization_level=kwargs["optimization_level"],
                         two_qubit_gates=sum(i.operation.num_qubits == 2 for i in isa.data),
                         depth=isa.depth(), seconds=perf_counter() - start))
        compiled.append(isa)
    with output.with_suffix(".qpy").open("wb") as f:
        qpy.dump(compiled, f)
    output.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def cost_cache_key(fake):
    """Canonical snapshot serialization; Target.__str__ has unstable ordering."""
    import inspect
    import qiskit
    properties = json.dumps(fake.properties().to_dict(), sort_keys=True, default=str).encode()
    return hashlib.sha256((ROOT / "swapprint" / "circuits.py").read_bytes() +
                          (ROOT / "swapprint" / "toy.py").read_bytes() +
                          inspect.getsource(cost_worker).encode() +
                          repr((STATE_SEED, SEEDS)).encode() + properties +
                          qiskit.__version__.encode()).hexdigest()[:12]


def gate_costs(refresh, start):
    # A cache changes with circuit-generating source or Qiskit/snapshot versions.
    from qiskit_ibm_runtime.fake_provider import FakeFez
    fake = FakeFez()
    digest = cost_cache_key(fake)
    rows, notes = [], []
    for target in ("all-to-all", "FakeFez"):
        for q in range(1, 12):
            output = CACHE / f"core_cost_{digest}_{target}_q{q}.json"
            if refresh or not output.exists():
                print(f"cost {target} q={q}: real transpilation (120 s limit)", flush=True)
                try:
                    subprocess.run([sys.executable, str(Path(__file__).resolve()), "--cost-worker",
                                    target, str(q), str(output)], check=True, timeout=120,
                                   cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8",
                                                 "QISKIT_NUM_PROCS": "1"})
                except subprocess.TimeoutExpired:
                    note = f"{target} q={q} exceeded 120 s; stopped at q={q-1}; no extrapolation."
                    notes.append(note)
                    print(note, flush=True)
                    break
            batch = json.loads(output.read_text(encoding="utf-8"))
            rows.extend(batch)
            print(f"cost {target} q={q}: " + "; ".join(
                f"{r['kind']} {r['two_qubit_gates']} 2q / depth {r['depth']}" for r in batch) +
                f"; elapsed {perf_counter()-start:.1f}s", flush=True)
            write_csv(RESULTS / "core_gate_costs.csv", rows)
    return rows, notes


def noisy_runs(refresh, start):
    from swapprint.toy import run
    rows, samples, notes = [], [], []

    def backend_runs(backend, qs):
        for q in qs:
            cases = [("random", p) for p in ("same", "near", "orthogonal") if q >= 2 or p != "near"]
            cases.append(("hadamard", "orthogonal"))
            for family, pair in cases:
                for kind in ("ancilla", "destructive"):
                    for seed in SEEDS:
                        key = f"core_sample_{backend.split(':')[1]}_{q}_{family}_{pair}_{kind}_{seed}.json"
                        cache = CACHE / key
                        if refresh or not cache.exists():
                            t = perf_counter()
                            result = run(q, pair, shots=SHOTS, backend=backend, kind=kind,
                                         family=family, seed=STATE_SEED, transpile_seed=seed,
                                         simulator_seed=4321 + seed, readout_cal=True,
                                         bootstrap_resamples=RESAMPLES)
                            result["seconds"] = perf_counter() - t
                            cache.write_text(json.dumps(result, indent=2), encoding="utf-8")
                        result = json.loads(cache.read_text(encoding="utf-8"))
                        row = {**result, "kind": kind, "transpile_seed": seed,
                               "p1_raw": result["p1_est"], "p1_cal": result["p1_est_cal"]}
                        rows.append({c: row[c] for c in NOISE_COLUMNS})
                        samples.append(dict(backend=backend, q=q, pair=pair, family=family,
                                            kind=kind, transpile_seed=seed,
                                            **result["sampling_details"]))
                        print(f"{backend} q={q} {family}/{pair} {kind} seed={seed}: "
                              f"raw={row['p1_raw']:.4f} cal={row['p1_cal']:.4f} "
                              f"ideal={row['p1_ideal']:.4f} 2q={row['two_qubit_gates']} "
                              f"depth={row['depth']} [{perf_counter()-start:.1f}s]", flush=True)
                        write_csv(RESULTS / "core_noise.csv", rows, NOISE_COLUMNS)

    t = perf_counter()
    backend_runs("aer-noisy:FakeFez", (1, 2, 3))
    base_seconds = sum(r["seconds"] for r in rows if r["backend"] == "aer-noisy:FakeFez")
    if base_seconds < 120:
        backend_runs("aer-noisy:FakeFez", (4,))
    fez_seconds = sum(r["seconds"] for r in rows if r["backend"] == "aer-noisy:FakeFez")
    notes.append(f"FakeFez measured circuit times q=1..3: {base_seconds:.2f}s; all included sizes: {fez_seconds:.2f}s (cached times count for optional-work decisions).")
    if not any(r["q"] == 4 for r in rows):
        notes.append("Skipped optional q=4: FakeFez q=1..3 circuit times exceeded the 120 s cheap-extension budget.")
    if fez_seconds < 300:
        backend_runs("aer-noisy:FakeBrisbane", (1, 2, 3))
    else:
        notes.append("Skipped FakeBrisbane because FakeFez took >=5 min.")
    (RESULTS / "core_noise_samples.json").write_text(json.dumps(samples, indent=2), encoding="utf-8")
    # Explicit gate-count spread with fixed states across the three routing seeds.
    spread = []
    keys = ("backend", "q", "family", "pair", "kind")
    for key in dict.fromkeys(tuple(r[k] for k in keys) for r in rows):
        selected = [r for r in rows if tuple(r[k] for k in keys) == key]
        counts = [r["two_qubit_gates"] for r in selected]
        spread.append(dict(zip(keys, key), minimum=min(counts), maximum=max(counts),
                           spread=max(counts)-min(counts)))
    write_csv(RESULTS / "core_noise_gate_spread.csv", spread)
    print(f"gate-count spread across seeds: {min(r['spread'] for r in spread)}.."
          f"{max(r['spread'] for r in spread)} two-qubit gates", flush=True)
    return rows, notes


def make_figure(noise, costs, thresholds):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from qiskit_ibm_runtime.fake_provider import FakeFez

    from swapprint import style
    style.use("white")
    plt.rcParams["legend.fontsize"] = 8
    cat = style.categorical("white")      # Carbon categorical: purple 70, cyan 50, teal 70
    colors = {"same": cat[0], "near": cat[1], "orthogonal": cat[2]}
    grey = style.CARBON["gray-60"]
    fig = plt.figure(figsize=(17, 7.2), layout="constrained")
    outer = fig.add_gridspec(1, 3, width_ratios=(1.45, 1, 1.12))
    left = outer[0].subgridspec(2, 1, hspace=.05)
    plotted = []
    # Show every routing seed, rather than treating seed variability as shot noise.
    fez = [r for r in noise if r["backend"] == "aer-noisy:FakeFez" and r["family"] == "random"]
    maxq = max(r["q"] for r in fez)
    for index, kind in enumerate(("ancilla", "destructive")):
        ax = fig.add_subplot(left[index])
        ax.set_title("(a) FakeFez: identical pairs leave zero" if index == 0 else "Destructive SWAP test", loc="left")
        if index == 0:
            ax.text(.02, .94, "Ancilla SWAP test", transform=ax.transAxes, va="top")
        for row in [r for r in fez if r["kind"] == kind]:
            x = row["q"] + {"same": -.24, "near": 0, "orthogonal": .24}[row["pair"]]
            x += (SEEDS.index(row["transpile_seed"]) - 1) * .035
            for estimate, offset, marker in (("raw", -.035, "o"), ("cal", .035, "s")):
                y = row[f"p1_{estimate}"]
                lo, hi = row[f"p1_{estimate}_lo"], row[f"p1_{estimate}_hi"]
                # Percentile limits need not bracket a clipped point estimate.
                ax.vlines(x+offset, lo, hi, color=colors[row["pair"]], lw=.8)
                ax.plot(x+offset, y, marker, ms=3.3, color=colors[row["pair"]],
                        mfc="white" if estimate == "cal" else colors[row["pair"]])
                plotted.append(dict(panel="a", series=estimate, x=x+offset, y=y, lo=lo, hi=hi,
                                    **row))
            if row["transpile_seed"] == SEEDS[0]:
                ax.plot(x, row["p1_ideal"], "_", color="black", ms=13, mew=1.4)
        ax.set(xlim=(.5, maxq+.5), ylim=(-.025, .57), xticks=range(1, maxq+1),
               ylabel="P(SWAP outcome = 1)")
        if index == 1:
            ax.set_xlabel("q (qubits per state); colour groups: same / near / orthogonal")
            handles = [Line2D([], [], color=c, lw=2, label=p) for p, c in colors.items()]
            handles += [Line2D([], [], color="black", marker=m, ls="", mfc=fc, label=l)
                        for m, fc, l in (("o", "black", "raw"), ("s", "white", "calibrated"), ("_", "black", "ideal"))]
            ax.legend(handles=handles, ncol=3, loc="upper center", bbox_to_anchor=(.5, -.24))
    ax = fig.add_subplot(outer[1])
    for target, ls in (("all-to-all", "--"), ("FakeFez", "-")):
        for component, kind, color, marker in (("preparation", "state", grey, "^"),
                                               ("swap", "ancilla", cat[0], "o"),
                                               ("swap", "destructive", cat[1], "s")):
            selected = [r for r in costs if r["target"] == target and r["component"] == component and r["kind"] == kind]
            ax.plot([r["q"] for r in selected], [r["two_qubit_gates"] for r in selected],
                    color=color, marker=marker, ms=3, ls=ls, label=f"{target}: {kind}")
            plotted.extend(dict(panel="b", series=f"{target}/{kind}", x=r["q"], y=r["two_qubit_gates"], **r) for r in selected)
    fake = FakeFez()
    gate = "cz" if "cz" in fake.target.operation_names else "ecr"
    error = float(np.median([p.error for p in fake.target[gate].values() if p is not None and p.error is not None]))
    guide = 1 / error
    ax.axhline(guide, color=style.ALERT, ls=":", lw=1.7)
    ax.text(1.1, guide*1.15, "Rough guide: one expected 2q-gate fault\n1 / median FakeFez gate error", color=style.CARBON["magenta-70"], fontsize=8)
    plotted.append(dict(panel="b", series="rough model guide", x=0, y=guide, median_gate_error=error))
    ax.set(title="(b) Real transpilation costs", xlabel="q (qubits per state)",
           ylabel="Two-qubit gates (count, log scale)", yscale="log", xticks=(1, 3, 5, 7, 9, 11))
    ax.set_ylim(bottom=.8)
    ax.text(.03, .97, "q=1 preparation uses 0 two-qubit gates\n(zero omitted on log scale)",
            transform=ax.transAxes, fontsize=8, va="top")
    ax.legend(loc="lower right")
    ax = fig.add_subplot(outer[2])
    f = np.logspace(-8, -.5, 500)
    independent = -np.expm1(4096 * np.log1p(-f))
    union = 4096 * f
    ax.plot(f, independent, color=cat[0], label="Independence: 1 − (1 − f)⁴⁰⁹⁶")
    ax.plot(f, union, color=cat[1], ls="--", label="Union bound: 4096 f")
    for series, values in (("independence", independent), ("union bound", union)):
        plotted.extend(dict(panel="c", series=series, x=float(x), y=float(y)) for x, y in zip(f, values))
    limit = -np.expm1(np.log(.99) / 4096)
    ax.axvspan(1e-8, limit, alpha=.15, color=cat[2])
    ax.axhline(.01, color=grey, ls=":")
    ax.text(1.4e-8, .035, "1% image target\nf ≲ 2.45 × 10⁻⁶\nextrapolated, not measured", fontsize=8)
    # A shot is one unit test for this measured baseline: k=1, tau=0.
    # Its false-alarm rate is exactly the measured same-pair ones / 4000.
    # Multi-shot table designs are plug-in tails, not measured rare-event rates.
    for row in [r for r in fez if r["pair"] == "same"]:
        value = row["p1_raw"]
        image_f = -np.expm1(4096 * np.log1p(-value))
        color = cat[0] if row["kind"] == "ancilla" else cat[1]
        ax.plot(value, image_f, "o" if row["kind"] == "ancilla" else "s", color=color, ms=5)
        plotted.append(dict(panel="c", series="measured k=1 tau=0 false alarm", x=value,
                            y=float(image_f), k=1, tau=0, **row))
    # Label each group once; stagger labels to keep adjacent q/kind groups legible.
    for q in range(1, maxq+1):
        for kind in ("ancilla", "destructive"):
            group = [r for r in fez if r["q"] == q and r["kind"] == kind and r["pair"] == "same"]
            value = float(np.mean([r["p1_raw"] for r in group]))
            image_f = -np.expm1(4096 * np.log1p(-value))
            level = {("ancilla", 1): .43, ("destructive", 1): .7,
                     ("ancilla", 2): .7, ("destructive", 2): .26,
                     ("ancilla", 3): .26, ("destructive", 3): .43}.get((kind, q), .16)
            ax.annotate(f"q{q} {'A' if kind=='ancilla' else 'D'}", (value, image_f),
                        xytext=(value, level), textcoords="data", ha="center", fontsize=8,
                        bbox=dict(facecolor="white", edgecolor="none", alpha=.9, pad=1),
                        arrowprops=dict(arrowstyle="-", color=style.CARBON["gray-50"], lw=.6))
    ax.set(xscale="log", yscale="log", xlim=(1e-8, .32), ylim=(1e-5, 2),
           xlabel="Per-tile false-alarm probability f", ylabel="Image false-alarm probability (4096 tiles)",
           title="(c) Small tile errors accumulate")
    ax.legend(loc="lower right")
    ax.text(.03, .08, "Markers: measured f = p(same),\nsingle-shot rule k=1, τ=0.\nA=ancilla; D=destructive.\n4000 shots cannot resolve f\nat the image target.",
            transform=ax.transAxes, fontsize=8)
    fig.suptitle(f"F6 — {LABEL}")
    fig.savefig(FIGURES / "core_noise.png", dpi=200)
    plt.close(fig)
    # Include controls and the second device as supplemental source values.
    plotted.extend(dict(panel="supplemental", series="raw+cal", **r) for r in noise if r not in fez)
    write_csv(FIGURES / "core_noise_data.csv", plotted)
    return dict(rough_guide_gate_count=guide, median_fez_two_qubit_error=error,
                image_target_f=float(limit))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--cost-worker", nargs=3, metavar=("TARGET", "Q", "OUTPUT"))
    args = parser.parse_args()
    if args.cost_worker:
        target, q, output = args.cost_worker
        cost_worker(target, int(q), Path(output))
        return
    start = perf_counter()
    for path in (RESULTS, FIGURES, CACHE):
        path.mkdir(parents=True, exist_ok=True)
    print(f"C2: {LABEL}; 4000 test + 2×4000 calibration shots; {RESAMPLES} bootstrap resamples", flush=True)
    rows, notes = noisy_runs(args.refresh, start)
    thresholds = threshold_table(rows)
    write_csv(RESULTS / "core_noise_threshold.csv", thresholds)
    for row in thresholds:
        print("threshold", row, flush=True)
    costs, cost_notes = gate_costs(args.refresh, start)
    guide = make_figure(rows, costs, thresholds)
    captions = {
        "core_noise.png": "Toy states on a simulated IBM device noise model (FakeFez, q=1–4, fixed random sign states, three transpiler seeds, 4000 shots per circuit): (a) individual-seed raw/independent-readout-calibrated p1 with 95% percentile parametric bootstrap intervals from 2000 joint test/calibration resamples and ideal ticks shows that noise lifts same pairs above zero, breaking the one-sided single-1 guarantee and requiring a threshold; (b) actual level-1 all-to-all and level-3 FakeFez transpilations of random near pairs and one state preparation show exponential preparation cost with a qualitative one-expected-gate-fault guide from the FakeFez median 2q error (not a universal device limit); (c) independence and union-bound image false alarms for 4096 tiles mark directly measured f=p1(same) for the per-unit single-shot rule k=1, τ=0 (flag ones/k > τ), while the separate table designs minimal multi-shot k and τ using exact binomial tails at worst-seed raw p(same) and least-separated p(near) for ≤1% false alarm and ≥99% power (q=1 uses orthogonal), conditional plug-in estimates rather than validated guarantees, and the 1% image target f ≲ 2.45×10⁻⁶ is extrapolated, not measured, and unresolved by 4000 shots.",
        "core_validation.png": "F7 compares exact SWAP probabilities with finite-shot ideal Aer circuit estimates for the validation pairs; these ideal-simulator checks do not establish performance for toy states on a simulated IBM device noise model."
    }
    # Keep the caption accurate if the optional fourth size was skipped.
    maxq = max(r["q"] for r in rows if r["backend"] == "aer-noisy:FakeFez")
    captions["core_noise.png"] = captions["core_noise.png"].replace("q=1–4", f"q=1–{maxq}")
    (FIGURES / "core_captions.json").write_text(json.dumps(captions, indent=2, ensure_ascii=False), encoding="utf-8")
    import qiskit, qiskit_aer, qiskit_ibm_runtime
    report = dict(label=LABEL, seconds=perf_counter()-start,
                  measured_circuit_seconds=sum(r["seconds"] for r in rows),
                  measured_transpilation_seconds=sum(r["seconds"] for r in costs),
                  cache_policy="Cached measurements and QPY transpilations retain their original measured times; seconds is this invocation's wall time.",
                  shots=SHOTS, calibration_shots_per_state=SHOTS,
                  bootstrap_resamples=RESAMPLES, state_seed=STATE_SEED, transpile_seeds=SEEDS,
                  simulator_seeds=[4321+s for s in SEEDS], optimization_level=3,
                  qiskit=qiskit.__version__, aer=qiskit_aer.__version__, runtime=qiskit_ibm_runtime.__version__,
                  notes=notes+cost_notes, **guide)
    (RESULTS / "core_noise_run.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"TOTAL {report['seconds']:.2f} s ({report['seconds']/60:.2f} min)", flush=True)


if __name__ == "__main__":
    main()
