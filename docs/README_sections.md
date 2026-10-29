# README sections from the quantum core (C4)

For Rashida to paste into `README.md`: three sections, "Design", "Encodings and measurement" and "Noise and
hardware". Figure paths are relative to the repo root. Bold bracketed items are placeholders. Each one says which
number goes there and where it comes from; fill them in before E6, or delete the sentence if the result never arrives.
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
random matrices. Ours is one fixed matrix, so the bound is a **heuristic**, which we check by measurement: the largest
overlap between tiles of different artworks is **[F3: pending: largest |overlap| among N distinct-content tile pairs, from `experiments/figures/collisions.png`]**,
against the bound's 0.508.

**What the verdict means.** By default, `compare` uses 32 shots per tile. "Tampered" means at least one SWAP test read
1, which on a noiseless test proves that tile changed. "No change detected" is **not** proof that nothing changed: the
reported miss bound, $3.6\times10^{-7}$ at 32 shots, is P(no detection | a tile changed), not P(unchanged | no detection).

**What it is not.** The code is public and injective, so a strict fingerprint can be decoded back to the image. It is
an integrity check, not a secret, a signature or a watermark. Simulating it gives no advantage over SHA-256 per tile,
which is better in practice (table T1). Buhrman et al.'s quantum advantage, $O(\log n)$ qubits against $\Theta(\sqrt n)$
classical bits, holds in the simultaneous-message model without shared randomness. Our verifier holds the reference,
so our setting is not that model. See `docs/THEORY.md` §6.

**Two backends.** `backend="exact"` is an analytical sampler: it computes each tile's overlap exactly and samples
its SWAP-test outcomes, identical in distribution to a noiseless circuit. `backend="aer"` runs real Qiskit SWAP-test
circuits for up to four selected tiles and uses the exact path for the rest. The tiles are picked by their classical
overlaps or by the user's click, so the Aer mode is a hybrid demonstration, not a purely quantum verifier.

## Encodings and measurement

The same SWAP test, three encodings, three meanings of "same":

| Mode | Unit | Qubits | What it encodes | Overlap | Flags a unit when |
|---|---|---|---|---|---|
| `strict` | 4×4 tile (4096) | 11 | codeword of a [2048, 384] code | $1 - 2d/2048$ | any shot reads 1 (32 shots) |
| `perceptual` | 64×64 region (16) | 6 | 64-bit DCT hash (pHash) | $1 - d/32$ | estimated overlap² < 0.52 (4096 shots) |
| `frqi` (baseline) | 4×4 tile (4096) | 7 | pixel values as angles | mean of $\cos(\theta_i - \theta'_i)$ | any shot reads 1 (32 shots) |

**Strict** catches any change, down to one bit. **Perceptual** asks whether the visible content changed: a JPEG re-save
flips a few hash bits and passes, while a splice or a pasted object flips many and is flagged. Two hashes of textured
regions differ in an even number of bits, so the threshold falls between 8 and 10 changed bits. At 4096 shots, 8 changed
bits are flagged with probability $5.3\times10^{-4}$ and 10 with probability 0.9997 (exact). Small edits, such as a short
caption, can pass by design; strict mode catches those. Calibrated on held-out artworks:
**[E3: pending: final threshold, benign false-alarm rate and content detection rate with N, from F4 `experiments/figures/perceptual_roc.png`]**.

**FRQI**, the standard "pixels as angles" encoding, is our baseline. A one-level change in one channel value gives
$p_1 = 2.96\times10^{-7}$ (exact), so the first 1 arrives after about 3.37 million shots on average, and 99% detection
needs 15,534,513 shots. The same edit in strict mode gives $p_1 \approx 0.5$. The encoding, not the measurement, decides
what the SWAP test can see. Figure F2 (`experiments/figures/encodings_shots_needed.png`) shows shots needed per edit
and per mode; F1 (`experiments/figures/detection_vs_shots.png`) shows strict detection against shots.

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

**Full-size fingerprints cannot run on today's hardware.** Preparing an arbitrary $q$-qubit sign state takes about
$2^q$ two-qubit gates. At $q = 11$, that is 2046 two-qubit gates all-to-all, and 3951 (depth 10,680) after routing on
FakeFez, a model of IBM's 156-qubit Heron r2 device. A whole strict SWAP test is 4167 two-qubit gates all-to-all. Panel
2 of F6 shows the growth from $q = 1$ to 11. So every noisy and hardware result here is a **measurement demonstration
on toy states** ($q \le 3$), not a full-size fingerprint.

**Noise study (F6, `experiments/figures/core_noise.png`).** Toy pairs at $q = 1, 2, 3$: identical (overlap 1),
orthogonal (overlap 0) and near (one sign flipped, overlap $1 - 2/2^q$), both SWAP-test kinds, 4000 shots, on Qiskit
Aer with the FakeFez noise model, `optimization_level=3` and a fixed transpiler seed.
**[F6: pending C2: p1 for identical and orthogonal pairs at each q and kind, with Wilson 95% intervals, two-qubit gate counts and depth, from the C2 results CSV (`experiments/results/core_*.csv`); one sentence on whether readout correction helped]**.
Noise lifts identical pairs off $p_1 = 0$, so a single 1 no longer proves a change, and a noisy run needs a threshold
(`compare(..., threshold=...)`). Over 4096 tiles, small per-tile false-alarm rates add up. In an independence model, a
1% whole-image false-alarm rate needs a per-tile rate below $2.45\times10^{-6}$ (union bound: $2.44\times10^{-6}$). That
is far below what 4000 shots can measure, so F6 marks that region as extrapolated.

**Hardware (F8).**
**[F8: pending C3. If it ran: "We ran toy SWAP tests (q = 1, 2; identical and orthogonal; both kinds; 4000 shots) on <device> on <date>, job ids in `experiments/results/core_hardware.json`. F8 (`experiments/figures/core_hardware.png`) shows them beside the FakeFez prediction: <one-line result>." If not: "Noise was simulated on FakeFez; we did not get hardware time."]**

**Copies.** Each shot consumes a copy of both states, and unknown quantum states cannot be cloned. A real deployment
would need a registrar to issue $k$ copies of every tile's state, 131,072 states for a 32-shot strict check, or a
quantum memory to hold them. Our simulator re-prepares states from the classical codeword for free, which is one more
reason it holds no advantage over a classical check.
