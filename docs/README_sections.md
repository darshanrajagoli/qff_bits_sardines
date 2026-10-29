# README sections from the quantum core (C4)

For Rashida to paste into `README.md`: three sections, "Design", "Encodings and measurement" and "Noise and
hardware". Figure paths are relative to the repo root. Reported results name their data sources below.
Every other number was produced by `swapprint` v0.2.0; `docs/THEORY.md` has the derivations and the calls.

---

## Design

SwapPrint turns each 4×4 patch of a 256×256 artwork into a quantum state, and compares two versions of the artwork patch
by patch with SWAP tests. It follows the quantum fingerprinting construction of Buhrman, Cleve, Watrous and de Wolf
(*PRL* 87, 167902, 2001): pass the data through an error-correcting code first, so that any change, however small,
moves the state far away.

1. **Canonical image.** `sp.load_image` gives a deterministic 256×256 RGB array on every machine.
2. **Tiles.** The image is cut into 64×64 = 4096 tiles of 4×4 pixels, 384 bits each.
3. **Code.** Each tile's bits $x$ go through a public pseudo-random linear [2048, 384] code, $E(x) = xG$. $G$ is expanded
   from a public seed with SHAKE-256, so everyone derives the same code.
4. **State.** The 2048-bit codeword sets the signs of an 11-qubit state,
   $|h_x\rangle = \frac{1}{\sqrt{2048}}\sum_i (-1)^{E(x)_i}|i\rangle$. Two tiles have overlap $1 - 2d/2048$, where $d$ is
   the number of code bits that differ.
5. **Compare.** A SWAP test on the registered and the candidate state reads 1 with probability
   $p_1 = (1 - \text{overlap}^2)/2$. An untouched tile gives $p_1 = 0$ and never reads 1. A tile is flagged at its first 1,
   and the flagged tiles form the tamper heatmap.

**What the code buys.** $G$ has GF(2) rank 384, so two different tiles never share a codeword. A one-bit change to a
tile flips 955 to 1080 of its 2048 code bits (all 384 single-bit changes, computed exactly), which gives $p_1 \ge 0.4977$.
A union bound over random codes gives $p_1 \ge 0.371$ for *every* changed tile, so 15 shots miss a changed tile with
probability at most $10^{-3}$, and 30 shots at most $10^{-6}$. That bound holds for all but a $10^{-6}$ fraction of
random matrices. Ours is one fixed matrix, so the bound is a **heuristic**. Among 1,000,000 sampled distinct-content strict tile pairs, maximum absolute overlap was 0.1083984375; no identical-content pairs were set aside. This supports, but does not certify, the fixed-code heuristic. Perceptual hashes matched for 345/26,880 distinct-content pairs: 1.283% (95% Wilson interval: 1.156%–1.425%). Source: `experiments/figures/collisions.csv`.

**What the verdict means.** By default, `compare` uses 32 shots per tile. "Tampered" means at least one SWAP test read
1. In the ideal noiseless model, identical inputs have zero probability of producing a 1; we flag a tile when a 1 is observed. "No change detected" is **not** proof that nothing changed: the
reported miss bound, $3.6\times10^{-7}$ at 32 shots, is a heuristic upper bound on P(no detection | a tile changed), not P(unchanged | no detection).

**What it is not.** The code is public and injective, so a strict fingerprint can be decoded back to the image. It is
an integrity check, not a secret, a signature or a watermark. The heatmap displays flagged 4×4 tiles. Finite-shot checks can miss changed tiles; unchanged tiles have exactly zero flag probability in the ideal model. The original image file need not be uploaded, but the stored strict fingerprint contains enough information to reconstruct the canonical image. Simulating it gives no advantage over SHA-256 per tile,
which is better in practice (table T1). Buhrman et al.'s quantum advantage, $O(\log n)$ qubits against $\Theta(\sqrt n)$
classical bits, holds in the simultaneous-message model without shared randomness. Our verifier holds the reference,
so our setting is not that model. See `docs/THEORY.md` §6.

**Two backends.** `backend="exact"` computes overlaps and samples the ideal SWAP-test distribution analytically.
App Verify uses the analytical sampler. The Aer button separately executes one classically selected unit.
Library `compare(backend="aer")` executes selected traced units—four by default—and samples the remainder analytically, making it a hybrid.

## Encodings and measurement

The same SWAP test, three encodings, three meanings of "same":

| Mode | Unit | Qubits | What it encodes | Overlap | Flags a unit when |
|---|---|---|---|---|---|
| `strict` | 4×4 tile (4096) | 11 | codeword of a [2048, 384] code | $1 - 2d/2048$ | any shot reads 1 (32 shots) |
| `perceptual` | 64×64 region (16) | 6 | 64-bit median DCT hash (flat cut-off 25) | $1 - d/32$ | estimated overlap² < 0.65 (2048 shots) |
| `frqi` (baseline) | 4×4 tile (4096) | 7 | pixel values as angles | mean of $\cos(\theta_i - \theta'_i)$ | any shot reads 1 (32 shots) |

**Strict** offers probabilistic sensitivity to canonical pixel changes, down to one bit. **Perceptual** remains the v0.2 median rule at E3 settings:
compare the 63 AC coefficients in the top-left 8×8 DCT block strictly above their median, fix bit 0 at zero,
and zero the entire hash when AC RMS is below 25. At t=0.65 and 2048 shots, flag a region at 359 ones.
Small edits can pass by design. On six held-out paintings (84 conditions), benign false alarm is
**2.78% [95% CI 0.00%, 8.33%]** and content detection is **65.14% [95% CI 59.45%, 70.83%]**. N = six held-out paintings (48 content and 36 benign conditions); intervals use an artwork bootstrap. Source: `experiments/results/perceptual_calibration.json`.
The default bits and perceptual version string remain identical to v0.2.1. The README, app and video
continue to use the v0.2 numbers.

**Ablation: a dead-zone hash.** A per-coefficient dead zone removes the flat-region cliff: synthetic stress benign false alarm falls from 37.78% to 0.157%, and mean JPEG 90 false alarm across 16 synthetic seeds from 62.93% to 0.059%. But at its E3-calibrated point (AC floor 10, t = 0.80, 4096 shots), held-out painting benign false alarm rises from 2.78% [95% CI 0.00%, 8.33%] to 14.09% [5.84%, 22.37%], while content detection rises from 65.14% [59.45%, 70.83%] to 72.95% [66.74%, 79.18%]. Intervals are 95% artwork bootstrap intervals (2000 resamples, seed 42). This did not generalise, so we kept v0.2 as the default and retained `rule="deadzone"` only as an ablation. Source: `experiments/results/core_perceptual_v3.json` / `.csv`; figure: `experiments/figures/core_perceptual_ablation.png`.

**FRQI**, the standard "pixels as angles" encoding, is our baseline. Its overlap averages $\cos(\theta_i-\theta_i^\prime)$ over 64 positions, including 16 padding positions; a one-channel one-level edit gives overlap ≈0.999999703552. A one-level change in one channel value gives
$p_1 \approx 2.964476322\times10^{-7}$ (rounded from the exact expression), so the first 1 arrives after about 3.37 million shots on average, and 99% detection
needs 15,534,513 shots. In strict mode, for the tested one-channel edits, the median exact budget for 99% detection across six held-out paintings is seven shots (`experiments/results/tamper_pairs.csv`). The encoding, not the measurement, decides
what the SWAP test can see. Figure F2 (`experiments/figures/encodings_shots_needed.png`) shows shots needed per edit
and per mode; its perceptual results use the historical median hash at t=0.52, separate from E3's t=0.65 default calibration.
F1 (`experiments/figures/detection_vs_shots.png`) shows strict detection against shots.

**Two SWAP tests.** The ancilla SWAP test uses $2q+1$ qubits (Hadamard, controlled-SWAPs, Hadamard, measure the
ancilla). The destructive SWAP test (Garcia-Escartin & Chamorro-Posada, *PRA* 87, 052330, 2013) uses $2q$ qubits: a
Bell measurement on each qubit pair, with outcome 1 when an odd number of pairs come out as singlets. Both have the
same $p_1$. State preparation is a Hadamard layer and a ±1 `DiagonalGate`. On Qiskit Aer, a full strict test (23
qubits) takes about 0.3 s on a laptop (`experiments/results/core_benchmark.json`).

**Validation (F7).** `python -m swapprint.validate` runs 50 unit pairs per SWAP-test kind (identical, one-pixel,
unrelated and intermediate perceptual pairs, across all three modes) as real Aer circuits at 2048 shots each. It checks
every estimate against the exact $p_1$ with a Wilson 95% interval:
97 of 100 Wilson 95% intervals contain the exact $p_1$ (67 of the 70 runs with $p_1 > 10^{-3}$; the 3 misses are 2.3σ-scale fluctuations in both directions, as expected for 95% intervals). Source: `experiments/results/core_validation.csv`.
See `experiments/figures/core_validation.png`.

## Noise and hardware

**Compilation costs (F6).** Preparing a generic sign state costs about $2^q$ two-qubit gates.
For F6's q=11 random-near ancilla circuit, the recorded all-to-all compilation has 4,180 two-qubit gates and depth 4,110; FakeFez compilation has 10,129 and depth 12,112. One preparation has 2,046 gates all-to-all and 3,757 on FakeFez, with routed depth 11,772. These are compilation results, not QPU executions. Source: `experiments/results/core_gate_costs.csv`.

**Noise study (F6, `experiments/figures/core_noise.png`).**
Noise was simulated in Aer using IBM device noise models FakeFez and FakeBrisbane on toy states with q=1–3. F6 is simulation only; F8 separately reports a real QPU toy-state run below.
Both SWAP-test kinds were sampled at 4000 shots per circuit and transpiler seeds 7, 23 and 91.
For the q=2 random identical-state ancilla circuit on simulated FakeFez at transpiler seed 23, 216/4,000 outcomes were one: raw $\hat p_1=0.0540$ [0.04725, 0.06100]; readout-corrected $\hat p_1=0.04975$ [0.04268, 0.05693]. These are 95% percentile parametric-bootstrap intervals from 2,000 joint test/calibration resamples, conditional on the simulated model. Readout correction leaves residual circuit error; this experiment does not identify its dominant mechanism. Source: `experiments/results/core_noise.csv` and `core_noise_run.json`.

Under independent tile decisions, image false-alarm probability is $1-(1-f)^{4096}$. A 1% image target requires $f\le2.4536923\times10^{-6}$; without independence, $f\le0.01/4096$ is sufficient by the union bound. The threshold table targets ≤1% false alarm and ≥99% power per toy unit using conditional plug-in binomial calculations, not validated image-level guarantees. The image target is extrapolated and unresolved by 4000 shots.

**Hardware (F8).** F8 reports toy states on ibm_marrakesh, a real IBM Heron r2 processor, on 2026-10-29 (job `dbhlpatep8hs73amdun0`): 18 toy comparisons at 4000 shots per PUB with 14 shared readout-calibration PUBs in one job. For the q=2 random same-pair ancilla test, 309/4000 outcomes were one: raw p1=0.07725 [0.06899, 0.08550]; readout-corrected p1=0.07166 [0.06272, 0.08048]. These are 95% percentile parametric-bootstrap intervals from 2000 joint test/calibration resamples, conditional on this run. Reported QPU usage was 36 seconds. Noise breaks the one-sided error guarantee; a threshold is needed. Readout correction leaves residual circuit error. This toy-state run establishes no full-image hardware performance: q = 11 remains far beyond today's hardware. Sources: `experiments/results/core_hardware.json` and `experiments/figures/core_hardware.png`.

**Copies.** Each independent shot needs a fresh copy of both states. A 4,096-tile, 32-shot check uses 131,072 reference states and 131,072 candidate states. Unknown states cannot be cloned; copies must be prepared or supplied. Known classical codewords allow repeated preparation, and copies may be processed sequentially. Quantum memory can store supplied copies but cannot create them.
