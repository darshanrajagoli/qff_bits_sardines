# SwapPrint: theory

Every number below comes from `swapprint` (v0.2.0, Qiskit 2.6.1). The last section lists the call that reproduces
each one. "Exact" means computed in closed form, not sampled.

## 1. Sign states and their overlap

A bit string $c \in \{0,1\}^m$ with $m = 2^q$ becomes a $q$-qubit state with equal-magnitude amplitudes and signs set
by the bits:

$$|h_c\rangle = \frac{1}{\sqrt m}\sum_{i=0}^{m-1} (-1)^{c_i}\,|i\rangle, \qquad \langle h_a|h_b\rangle = 1 - \frac{2\,d(a,b)}{m},$$

where $d$ is Hamming distance. The overlap is real and lies in $[-1, 1]$. Equal strings give $1$, strings differing in
half their positions give $0$, and complementary strings give $-1$: the same state up to a global phase.

## 2. The SWAP test

**Ancilla version** ($2q+1$ qubits): Hadamard on an ancilla, a controlled-SWAP of each qubit pair of the two registers,
Hadamard, measure the ancilla. It reads 1 with probability

$$p_1 = \frac{1 - |\langle a|b\rangle|^2}{2}.$$

* In the ideal noiseless model, identical inputs have zero probability of producing a 1; we flag a tile when a 1 is observed. The error is one-sided.
* Orthogonal states give $p_1 = \tfrac12$.
* $k$ independent shots miss a difference with probability $(1-p_1)^k$.
* The test sees only $|\langle a|b\rangle|^2$, so overlaps near $-1$ are as bad as overlaps near $+1$.

**Destructive version** ($2q$ qubits, no ancilla; Garcia-Escartin & Chamorro-Posada, *PRA* 87, 052330, 2013): for each
pair $(a_i, b_i)$ apply CNOT $a_i \to b_i$ and then H on $a_i$, and measure all $2q$ qubits. This is a Bell-basis
measurement of each pair, and the outcome counts as 1 when $\sum_i a_i b_i$ is odd (an odd number of singlets). It has
the same $p_1$. It saves the ancilla and all the controlled-SWAPs, but it consumes both states.

The Aer circuits in `swapprint.circuits` implement both. Validation (figure F7, `experiments/figures/core_validation.png`)
compares 2048-shot Aer estimates with the exact $p_1$ on 50 unit pairs per kind:
97 of 100 Wilson 95% intervals contain the exact $p_1$ (67 of the 70 runs with $p_1 > 10^{-3}$; the 3 misses are 2.3σ-scale fluctuations in both directions, as expected for 95% intervals). Source: `experiments/results/core_validation.csv`.

## 3. Strict mode: the [2048, 384] code

A 4×4 tile holds $n = 4\cdot4\cdot3\cdot8 = 384$ bits $x$. A public generator matrix $G \in \mathbb{F}_2^{384\times2048}$,
expanded from the seed `qff-sardines-2026` with SHAKE-256, maps it to the codeword $E(x) = xG$, which becomes the
11-qubit sign state $|h_{E(x)}\rangle$. The code is linear, so $E(x)\oplus E(y) = E(x\oplus y)$ and the overlap of two
tiles depends only on the weight $w$ of $E(x\oplus y)$: $\langle h_{E(x)}|h_{E(y)}\rangle = 1 - 2w/2048$.

**The two-tailed union bound.** For a uniformly random $G$, each nonzero message's codeword has weight
$\mathrm{Bin}(m, \tfrac12)$. A tile pair is bad if $w \le d$ (overlap near $+1$) or $w \ge m-d$ (near $-1$). A union bound
over the $2^n - 1$ nonzero messages and both tails gives

$$\Pr_G[\text{some nonzero codeword has } w \le d \text{ or } w \ge m-d] \;\le\; 2^{n+1}\,\Pr[\mathrm{Bin}(m,\tfrac12) \le d].$$

`code_info()` takes the largest $d$ for which this is at most $10^{-6}$. Under this random-code heuristic, every nonzero codeword has weight in
$[504, 1544]$, so every changed tile has $|\text{overlap}| \le 0.5078125$ and $p_1 \ge 0.371063232421875$.

| target miss probability per changed tile | $10^{-2}$ | $10^{-3}$ | $10^{-6}$ | $10^{-9}$ |
|---|---|---|---|---|
| shots, $k = \lceil \ln(\text{miss}) / \ln(1-p_{1,\min}) \rceil$ | 10 | 15 | 30 | 45 |

At the default 32 shots the heuristic upper bound on P(no detection | changed) is
$(1-p_{1,\min})^{32} \approx 3.6\times10^{-7}$, using $p_{1,\min}=0.371063232421875$ (`Comparison.miss_bound`).

**Why this is only heuristic for our code.** The statement is about a random $G$: all but a $10^{-6}$ fraction of
matrices are good. Ours is one fixed matrix, and SHAKE-256 output behaving like random bits is an assumption, not a
proof. Certifying the minimum distance of a [2048, 384] code means ruling out low-weight words among $2^{384}$, which is
infeasible. So we call 0.371 and 30 shots a heuristic bound and back it with measurements on our actual $G$:

* all 384 single-bit changes (exact): codeword weights 955 to 1080, so $|\text{overlap}| \le 0.0674$ and $p_1 \ge 0.4977$
* 100,000 random nonzero messages (seed 0): largest $|\text{overlap}| = 0.0957$, smallest $p_1 = 0.4954$
* F3 (`experiments/figures/collisions.png`): Among 1,000,000 sampled distinct-content strict tile pairs, maximum absolute overlap was 0.1083984375; no identical-content pairs were set aside. This supports, but does not certify, the fixed-code heuristic. Perceptual hashes matched for 345/26,880 distinct-content pairs: 1.283% (95% Wilson interval: 1.156%–1.425%). Source: `experiments/figures/collisions.csv`.

A typical change gives $p_1 \approx 0.5$, so in practice a changed tile reads 1 about every second shot.

**Injective, so not secret.** $G$ has GF(2) rank 384, so $E$ is injective: two different tiles never share a codeword,
and anyone holding a strict fingerprint can solve $xG = c$ and recover the canonical image. The all-ones word is not a
codeword (adding it raises the rank to 385), so no two tiles differ only by a global phase. A fingerprint is an
integrity check, not a way to hide the artwork.

## 4. Perceptual mode: a median hash, then a sign state

The default remains the v0.2 median rule (`PERCEPTUAL_RULE = "median"`) at E3 settings:
`PHASH_FLAT_SIGMA = 25.0`, `PERCEPTUAL_F_THRESHOLD = 0.65`, and `PERCEPTUAL_SHOTS = 2048`.
Each 64×64 region uses integer luminance $Y=(299R+587G+114B+500)//1000$, then 2×2 box averaging to
32×32 float64 and an orthonormal DCT-II. Flatten the top-left 8×8 block row-major, omit DC, and
compare the 63 AC coefficients strictly above their median; bit 0 is fixed at zero. If AC RMS is
below 25, all bits are zero. The 64 bits define a 6-qubit sign state with overlap $1-d/32$.
Default fingerprint bits and the version `swapprint-0.1/perceptual/q6/r64/flat25.0` are unchanged
from v0.2.1; the package version remains 0.3.0 for the rule option and style module.

Flag a region when $\hat F=\max(0,1-2\,\mathrm{ones}/2048)<0.65$, exactly when `ones >= 359`.
For distance $d$, $p_1=(1-(1-d/32)^2)/2$; the exact flag probability is
$P[\mathrm{Binomial}(2048,p_1)\ge359]$. The ideal distance interval is $7\le d\le57$;
this is two-sided because complementary signs represent the same state up to global phase.
Image flag probability is $1-\prod_{u=1}^{16}(1-P_u)$. Ties at the median can reduce hash weight;
small edits can pass, and crossing the whole-region RMS cutoff can cause benign false alarms.

E3 selected these settings on six calibration paintings, then evaluated six held-out paintings
(84 conditions): benign false alarm is 2.78% [95% CI 0.00%, 8.33%] and content detection is
65.14% [95% CI 59.45%, 70.83%]. N = six held-out paintings (48 content and 36 benign conditions); these are 95% artwork-bootstrap intervals around exact probabilities. Source: `experiments/results/perceptual_calibration.json`.
The README, app and video continue to use these v0.2 results.

**Ablation: a dead-zone hash.** A per-coefficient dead zone removes the flat-region cliff: synthetic stress benign false alarm falls from 37.78% to 0.157%, and mean JPEG 90 false alarm across 16 synthetic seeds from 62.93% to 0.059%. But at its E3-calibrated point (AC floor 10, t = 0.80, 4096 shots), held-out painting benign false alarm rises from 2.78% [95% CI 0.00%, 8.33%] to 14.09% [5.84%, 22.37%], while content detection rises from 65.14% [59.45%, 70.83%] to 72.95% [66.74%, 79.18%]. Intervals are 95% artwork bootstrap intervals (2000 resamples, seed 42). This did not generalise, so we kept v0.2 as the default and retained `rule="deadzone"` only as an ablation. Source: `experiments/results/core_perceptual_v3.json` / `.csv`; figure: `experiments/figures/core_perceptual_ablation.png`.

## 5. FRQI: why "pixels as angles" fails

FRQI puts value $v$ into the angle $\theta = (\pi/2)\,v/255$:
$|I\rangle = \tfrac18\sum_{i=0}^{63}(\cos\theta_i|0\rangle + \sin\theta_i|1\rangle)|i\rangle$ on 6 + 1 qubits, with
48 channel values per tile and 16 padding positions at $\theta = 0$. Then

$$\langle I|I'\rangle = \frac{1}{64}\sum_{i=0}^{63}\cos(\theta_i - \theta'_i).$$

A one-level change of one channel value moves one angle by $\pi/510$, so
$\text{overlap}=(63+\cos(\pi/510))/64 \approx 0.999999703552$ and
$p_1=(1-\text{overlap}^2)/2 \approx 2.964476322\times10^{-7}$.
The expressions are exact; the displayed decimal values are rounded. The first 1 arrives after $1/p_1 \approx 3.37$ million shots
on average; 99% detection needs 15,534,513 shots and a $10^{-6}$ miss needs 46,603,539. The encoding is smooth: a small
edit is a small rotation, quadratic in the change and diluted by $1/64$. A code is deliberately the opposite. It sends
any change, however small, to a far-away state. The SWAP test is the same in both cases; only the encoding differs.

## 6. What Buhrman, Cleve, Watrous & de Wolf prove, and what it does not mean here

*PRL* 87, 167902 (2001). In the **simultaneous-message model without shared randomness**, Alice and Bob each send one
message about their $n$-bit input to a referee, who must decide whether the inputs are equal. Code-based quantum
fingerprints need $O(\log n)$ qubits, while any classical protocol needs $\Theta(\sqrt n)$ bits. That is a proven
separation in that model. SwapPrint uses the same construction, with sign phases in place of the paper's extra qubit
(our overlap is $1 - 2d/m$ rather than $1 - d/m$).

What it does **not** mean for us:

* **Our setting is not that model.** The verifier holds the registered fingerprint, and the code is public, so it could
  compare classically. With shared public randomness, classical equality has constant communication at fixed error.
  SHA-256 is our practical stored-reference baseline; its fixed digest is not an unconditional worst-case equality theorem.
* **Our image experiment uses classical simulation**, which computes the overlap exactly. Sampling it adds noise and no power. F8 separately tests small toy states on a real IBM QPU.
* **At our sizes the asymptotics say little.** Per tile, $n = 384$, so $\sqrt n \approx 19.6$ bits against 11 qubits,
  and the theorem fixes no constants. A whole-image fingerprint at the same code rate ($n = 1{,}572{,}864$) would take
  $q = 23$ qubits against $\sqrt n \approx 1254$ bits, but a 47-qubit SWAP test cannot be simulated as a statevector.

So there is **no quantum advantage in our setting**, and in practice SHA-256 per tile is the better integrity check:
32 bytes per tile, milliseconds per image, and no copies needed (table T1). What we contribute is a study of encoding
and measurement.

## 7. No-cloning: shots cost copies

Each independent shot needs a fresh copy of both states. A 4,096-tile, 32-shot check uses 131,072 reference states and 131,072 candidate states. Unknown states cannot be cloned; copies must be prepared or supplied. Known classical codewords allow repeated preparation, and copies may be processed sequentially. Quantum memory can store supplied copies but cannot create them.

## 8. State preparation costs about $2^q$ two-qubit gates

A sign state with arbitrary signs is a Hadamard layer followed by a diagonal of $\pm1$ entries. For generic signs the
diagonal is fully entangling, and its two-qubit gate count grows like $2^q$. F6 uses Qiskit 2.6.1,
random-near states (`state_seed=2026`), `seed_transpiler=7`, optimization level 1 for all-to-all and 3 for FakeFez.
The table reports one state preparation from `experiments/results/core_gate_costs.csv`:

| $q$ | 3 | 5 | 7 | 9 | 11 |
|---|---|---|---|---|---|
| all-to-all, basis {cx, rz, sx, x}: two-qubit gates | 6 | 30 | 126 | 510 | 2046 |
| FakeFez (routed): two-qubit gates | 9 | 40 | 198 | 980 | 3757 |
| FakeFez depth | 35 | 166 | 667 | 2641 | 11,772 |

For F6's q=11 random-near ancilla circuit, the recorded all-to-all compilation has 4,180 two-qubit gates and depth 4,110; FakeFez compilation has 10,129 and depth 12,112. One preparation has 2,046 gates all-to-all and 3,757 on FakeFez, with routed depth 11,772. These are compilation results, not QPU executions. Source: `experiments/results/core_gate_costs.csv`.

Noise was simulated in Aer using IBM device noise models FakeFez and FakeBrisbane on toy states with q=1–3. F8 reports toy states on ibm_marrakesh, a real IBM Heron r2 processor, on 2026-10-29 (job `dbhlpatep8hs73amdun0`): 18 toy comparisons at 4000 shots per PUB with 14 shared readout-calibration PUBs in one job. For the q=2 random same-pair ancilla test, 309/4000 outcomes were one: raw p1=0.07725 [0.06899, 0.08550]; readout-corrected p1=0.07166 [0.06272, 0.08048]. These are 95% percentile parametric-bootstrap intervals from 2000 joint test/calibration resamples, conditional on this run. Reported QPU usage was 36 seconds. Noise breaks the one-sided error guarantee; a threshold is needed. Readout correction leaves residual circuit error. This toy-state run establishes no full-image hardware performance: q = 11 remains far beyond today's hardware. Sources: `experiments/results/core_hardware.json` and `experiments/figures/core_hardware.png`.

## Reproduce the numbers

```python
import swapprint as sp, numpy as np, math
sp.code_info()                                    # d_min_guaranteed 504, overlap_max 0.5078125, p1_min 0.371063
[sp.shots_needed(m, sp.code_info()["p1_min"]) for m in (1e-2, 1e-3, 1e-6, 1e-9)]   # [10, 15, 30, 45]
G = sp.codes.generator_matrix(); w = G.sum(1)     # single-bit changes: weights 955..1080
X = np.random.default_rng(0).integers(0, 2, (100_000, 384))
ov = 1 - 2 * sp.codes.encode(X).sum(1) / 2048     # random messages: max |ov| 0.0957
p = (1 - (1 - (1 - math.cos(math.pi / 510)) / 64) ** 2) / 2                       # FRQI one level: 2.96e-7
sp.shots_needed(0.01, p)                          # 15534513
```

GF(2) rank: Gaussian elimination of `G` mod 2 gives 384, or 385 with the all-ones row appended. The state-preparation
table transpiles `sp.circuits._sign_state_circuit(c)` for each $q$.
