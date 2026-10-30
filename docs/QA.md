# SwapPrint: judge Q&A

Numbers come from `swapprint` and the CSVs in `experiments/`; the derivations are in `docs/THEORY.md`.
Image experiments and F6 use classical simulation; F8 separately measures toy states on a real IBM QPU. Data sources are named below.

## The 20-second pitch

> SwapPrint gives every 4×4 patch of an artwork an 11-qubit quantum fingerprint, using the error-correcting-code
> construction of Buhrman et al. A SWAP test compares fingerprints. In an ideal noiseless test, untouched patches never trigger it; a changed patch
> typically triggers it about half the time. Thirty shots give a heuristic upper bound of 10⁻⁶ on P(no detection | changed); flagged tiles show the location. The usual
> "pixels as angles" encoding would need millions of shots for the same edit. Our experiments measure all of this, and
> what IBM-device noise does to small versions of the circuit.

## Questions

**1. Why quantum at all?**
Problem 5 asks for a circuit-based fingerprint and a verification experiment, and the textbook quantum one exists:
Buhrman et al. (2001). We use it to study how encoding and measurement decide what a quantum comparison can detect.
We claim no advantage: our setting is not the model where their advantage holds, and our full-image experiment is classically simulated. F8 separately measures small toy states on a real IBM QPU.

**2. Isn't this just a hash? How does it compare with SHA-256?**
Classically, strict mode is an injective linear code: closer to a checksum than to a cryptographic hash. SHA-256 per
tile catches every changed tile with one comparison and 32 bytes. We need 32 shots per tile, 1 MiB of codeword bits per
image, and fresh state copies per shot. Table T1 puts them side by side.

**3. So why not just use SHA-256?**
In practice you should, and the README says so. SwapPrint is an experiment on encoding and measurement: why one SWAP
test detects a one-pixel edit in a few shots under one encoding and needs millions under another.

**4. Explain the SWAP test.**
Hadamard an ancilla, controlled-SWAP the two registers, Hadamard again, measure: it reads 1 with probability
$(1 - \lvert\langle a|b\rangle\rvert^2)/2$. In the ideal noiseless model, identical inputs have zero probability of producing a 1; we flag a tile when a 1 is observed. We also run
the destructive version (Garcia-Escartin & Chamorro-Posada 2013): Bell measurements on the pairs, no ancilla, same $p_1$.

**5. What does the error-correcting code do?**
It spreads any change across the codeword. A one-bit change in a tile flips 955 to 1080 of the 2048 code bits on our
matrix (all 384 cases computed exactly), so the overlap is at most 0.067 in absolute value and $p_1 \ge 0.4977$:
nearly orthogonal states, from the smallest possible edit.

**6. Why does FRQI fail?**
Its overlap is the average of $\cos(\theta_i - \theta'_i)$ over 64 positions. A one-level change moves one angle by
$\pi/510$, so $p_1 \approx 2.964476322\times10^{-7}$ (rounded): on average 3.37 million shots to the first 1, and 15.5 million for 99%
detection. A smooth encoding turns a small edit into a small rotation; a code turns it into a far-away state.

**7. Why 4×4 tiles and 11 qubits?**
A 4×4 RGB tile is 384 bits. A code of length $2^{11}$ gives a heuristic $p_{1,\min} \approx 0.371$ (30 shots for a heuristic $10^{-6}$ miss upper bound), against
0.256 and 47 shots at $q = 10$. At $q = 11$ the ancilla test is 23 qubits, about 0.3 s per run on Aer on a laptop.
The 4096 tiles also make the heatmap that shows where the image changed.

**8. What exactly is guaranteed, and what is heuristic?**
Exact: equal tiles never read 1 on a noiseless test, the code is injective (rank 384), and $p_1 = (1 - \text{overlap}^2)/2$.
Heuristic: $p_1 \ge 0.371$ for every changed tile, and hence the 30-shot miss bound. That bound holds for all but $10^{-6}$
of random codes; ours is one fixed SHAKE-256 matrix, so we back it with measurements (THEORY §3, F3).

**9. Can a forger fool it?**
There is no key: the code is public and linear, and a strict fingerprint can even be decoded back to the image. Anyone
who can replace the reference fingerprint wins. Against a trusted reference, an edit escapes only with probability
$(1-p_1)^k$; the bound is statistical, not cryptographic. This is an integrity check, not a signature or a watermark.

**10. What does "no change detected" mean?**
Only that no shot read 1. It is not proof that nothing changed. The miss bound $(1-p_{1,\min})^{k}$, $3.6\times10^{-7}$ at
32 shots, is P(no detection | a tile changed), a heuristic upper bound. It is not P(unchanged | no detection), which
would need a prior on edits.

**11. What is perceptual mode for?**
To ask "did the visible content change?" The default remains the v0.2 median DCT hash: compare 63 AC
coefficients with their median, fix bit 0 at zero, and zero all bits below AC RMS 25. E3 settings are
t=0.65 and 2048 shots (a region flags at 359 ones). On six held-out paintings, benign false alarm is
2.78% [95% CI 0.00%, 8.33%] and content detection is 65.14% [95% CI 59.45%, 70.83%]. N = six held-out paintings, with 48 content and 36 benign conditions; intervals are 95% artwork bootstrap (`experiments/results/perceptual_calibration.json`). Small edits can
pass by design. Default bits and the perceptual version string are unchanged from v0.2.1.

**12. Why simulate the exact statistics instead of always running circuits?**
A full image is 4096 tiles × 32 shots = 131,072 SWAP tests, each a 23-qubit circuit. The exact backend computes each
tile's overlap and samples its outcomes, identical in distribution to a noiseless circuit. Aer runs the real circuits
for selected tiles (`backend="aer"`), which keeps the app interactive.

**13. How did you validate that?**
`python -m swapprint.validate` runs 50 unit pairs per SWAP-test kind on Aer at 2048 shots each, covering all three modes
(identical, one-pixel, unrelated, and intermediate perceptual pairs), and checks each against the exact $p_1$ with a
Wilson 95% interval. 97 of 100 contain it.

**14. Who picks the tiles that run as circuits?**
The classical overlaps (the most suspicious tiles first) or the user's click. So the Aer mode is a hybrid
demonstration, never a purely quantum verifier, and we label it that way.

**15. Ancilla or destructive SWAP test: which do you use?**
Both give the same $p_1$; F7 validates both. Destructive needs $2q$ qubits instead of $2q+1$ and no controlled-SWAPs,
so it is the cheaper choice for noisy toy runs. The ancilla version is the one people know, so the app draws it first.

**16. What does noise do?**
Noise lifts identical pairs off $p_1 = 0$, so the ideal single-1 decision rule needs a threshold.
For the q=2 random identical-state ancilla circuit on simulated FakeFez at transpiler seed 23, 216/4,000 outcomes were one: raw $\hat p_1=0.0540$ [0.04725, 0.06100]; readout-corrected $\hat p_1=0.04975$ [0.04268, 0.05693]. These are 95% percentile parametric-bootstrap intervals from 2,000 joint test/calibration resamples, conditional on the simulated model. Readout correction leaves residual circuit error; this experiment does not identify its dominant mechanism. Source: `experiments/results/core_noise.csv` and `core_noise_run.json`.

Under independent tile decisions, image false-alarm probability is $1-(1-f)^{4096}$. A 1% image target requires $f\le2.4536923\times10^{-6}$; without independence, $f\le0.01/4096$ is sufficient by the union bound. The threshold table targets ≤1% false alarm and ≥99% power per toy unit using conditional plug-in binomial calculations, not validated image-level guarantees. The image target is extrapolated and unresolved by 4000 shots.

**17. Did you use hardware?**
F8 reports toy states on ibm_marrakesh, a real IBM Heron r2 processor, on 2026-10-29 (job `dbhlpatep8hs73amdun0`): 18 toy comparisons at 4000 shots per PUB with 14 shared readout-calibration PUBs in one job. For the q=2 random same-pair ancilla test, 309/4000 outcomes were one: raw p1=0.07725 [0.06899, 0.08550]; readout-corrected p1=0.07166 [0.06272, 0.08048]. These are 95% percentile parametric-bootstrap intervals from 2000 joint test/calibration resamples, conditional on this run. Reported QPU usage was 36 seconds. Noise breaks the one-sided error guarantee; a threshold is needed. Readout correction leaves residual circuit error. This toy-state run establishes no full-image hardware performance: q = 11 remains far beyond today's hardware. Sources: `experiments/results/core_hardware.json` and `experiments/figures/core_hardware.png`.

**18. How would it work for real?**
Each independent shot needs a fresh copy of both states. A 4,096-tile, 32-shot check uses 131,072 reference states and 131,072 candidate states. Unknown states cannot be cloned; copies must be prepared or supplied. Known classical codewords allow repeated preparation, and copies may be processed sequentially. Quantum memory can store supplied copies but cannot create them.

For F6's q=11 random-near ancilla circuit, the recorded all-to-all compilation has 4,180 two-qubit gates and depth 4,110; FakeFez compilation has 10,129 and depth 12,112. One preparation has 2,046 gates all-to-all and 3,757 on FakeFez, with routed depth 11,772. These are compilation results, not QPU executions. Source: `experiments/results/core_gate_costs.csv`.

**19. What are the limitations?**
No advantage over SHA-256, which is better in practice. The 30-shot bound is heuristic. Fingerprints are public and
decodable, so they are not secret. Noise breaks the one-sided test, full-size circuits are far too deep for today's
hardware, and perceptual mode misses small edits by design. The image experiments are classically simulated; F8 separately measures small toy states on a real IBM QPU.

**20. What would you do next?**
Run the referee protocol, where Alice and Bob each send a fingerprint and the referee only SWAP-tests, which is the
setting Buhrman et al. analyse. Search our fixed code for low-weight codewords to test the heuristic directly. And
compare cheaper, low-depth state families on hardware.

**Did you try a better hash?** Yes, a dead-zone hash removed the synthetic flat-region cliff but raised held-out benign false alarms from 2.78% to 14.09% at its E3-calibrated point, so we kept v0.2 and retained it only as an ablation (THEORY §4; `experiments/figures/core_perceptual_ablation.png`).
