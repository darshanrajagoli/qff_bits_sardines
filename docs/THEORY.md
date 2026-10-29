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

* Identical states give $p_1 = 0$ exactly, so a single 1 proves the inputs differ. The error is one-sided.
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

`code_info()` takes the largest $d$ for which this is at most $10^{-6}$. The result: every nonzero codeword has weight in
$[504, 1544]$, so every changed tile has $|\text{overlap}| \le 0.5078125$ and $p_1 \ge 0.3711$.

| target miss probability per changed tile | $10^{-2}$ | $10^{-3}$ | $10^{-6}$ | $10^{-9}$ |
|---|---|---|---|---|
| shots, $k = \lceil \ln(\text{miss}) / \ln(1-p_{1,\min}) \rceil$ | 10 | 15 | 30 | 45 |

At the default 32 shots the bound is $(1-0.3711)^{32} = 3.6\times10^{-7}$ (`Comparison.miss_bound`).

**Why this is only heuristic for our code.** The statement is about a random $G$: all but a $10^{-6}$ fraction of
matrices are good. Ours is one fixed matrix, and SHAKE-256 output behaving like random bits is an assumption, not a
proof. Certifying the minimum distance of a [2048, 384] code means ruling out low-weight words among $2^{384}$, which is
infeasible. So we call 0.371 and 30 shots a heuristic bound and back it with measurements on our actual $G$:

* all 384 single-bit changes (exact): codeword weights 955 to 1080, so $|\text{overlap}| \le 0.0674$ and $p_1 \ge 0.4977$
* 100,000 random nonzero messages (seed 0): largest $|\text{overlap}| = 0.0957$, smallest $p_1 = 0.4954$
* tiles of different artworks (F3, `experiments/figures/collisions.png`): **[F3: pending: "largest |overlap| among N distinct-content tile pairs = X", and how many identical-content pairs were set aside; from Rashida's E2 collision experiment]**

A typical change gives $p_1 \approx 0.5$, so in practice a changed tile reads 1 about every second shot.

**Injective, so not secret.** $G$ has GF(2) rank 384, so $E$ is injective: two different tiles never share a codeword,
and anyone holding a strict fingerprint can solve $xG = c$ and recover the canonical image. The all-ones word is not a
codeword (appending it raises the rank to 385), so no two tiles differ only by a global phase. A fingerprint is an
integrity check, not a way to hide the artwork.

## 4. Perceptual mode: a hash, then a sign state

Each 64×64 region is reduced to a 64-bit pHash: integer luminance, 2×2 box average to 32×32, orthonormal DCT-II, the
63 lowest-frequency AC coefficients compared with their median, plus bit 0 fixed at 0. A region whose AC RMS is below
`PHASH_FLAT_SIGMA` = 25 counts as flat and hashes to all zeros. The hash becomes a 6-qubit sign state with overlap
$1 - d/32$.

A region is flagged when the estimate $\hat F = \max(0, 1 - 2\,\text{ones}/\text{shots})$ of $F = \text{overlap}^2$ falls
below `PERCEPTUAL_F_THRESHOLD` = 0.52, which is $|\text{overlap}| < 0.721$, i.e. $9 \le d \le 55$. A non-flat hash has
exactly 31 ones (median split), so two non-flat hashes differ in an even number of bits: in practice the threshold sits
between $d = 8$ and $d = 10$. At the default 4096 shots, the exact flag probability is $5.3\times10^{-4}$ at $d=8$,
$0.9997$ at $d=10$, and below $10^{-29}$ for $d \le 6$. Unlike strict mode, this is a two-sided statistical test.

The threshold 0.52 is a starting value from four Met paintings.
**[E3: pending: the threshold, flat σ and shot count calibrated on held-out artworks, with the benign false-alarm and content detection rates and their N; from Rashida's E3 / figure F4 `perceptual_roc.png`]**.
Small edits such as a short caption can stay under the threshold, by design.

## 5. FRQI: why "pixels as angles" fails

FRQI puts value $v$ into the angle $\theta = (\pi/2)\,v/255$:
$|I\rangle = \tfrac18\sum_{i=0}^{63}(\cos\theta_i|0\rangle + \sin\theta_i|1\rangle)|i\rangle$ on 6 + 1 qubits, with
48 channel values per tile and 16 padding positions at $\theta = 0$. Then

$$\langle I|I'\rangle = \frac{1}{64}\sum_{i=0}^{63}\cos(\theta_i - \theta'_i).$$

A one-level change of one value moves one angle by $\pi/510$, so $1 - \text{overlap} = (1-\cos(\pi/510))/64 =
2.96\times10^{-7}$ and $p_1 = 2.96\times10^{-7}$ (exact). The first 1 arrives after $1/p_1 \approx 3.37$ million shots
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
  compare classically. With public randomness, or simply a public hash such as SHA-256, classical equality testing
  needs a constant number of bits, independent of $n$.
* **Our run is a classical simulation**, which computes the overlap exactly. Sampling it adds noise and no power.
* **At our sizes the asymptotics say little.** Per tile, $n = 384$, so $\sqrt n \approx 19.6$ bits against 11 qubits,
  and the theorem fixes no constants. A whole-image fingerprint at the same code rate ($n = 1{,}572{,}864$) would take
  $q = 23$ qubits against $\sqrt n \approx 1254$ bits, but a 47-qubit SWAP test cannot be simulated as a statevector.

So there is **no quantum advantage in our setting**, and in practice SHA-256 per tile is the better integrity check:
32 bytes per tile, milliseconds per image, and no copies needed (table T1). What we contribute is a study of encoding
and measurement.

## 7. No-cloning: shots cost copies

A shot needs a fresh copy of both states. The destructive test measures them outright. The ancilla test leaves them
disturbed whenever they differ, and the verifier cannot know in advance whether they do. So $k$ shots need $k$ copies of
each fingerprint state, and an unknown state cannot be cloned, so the copies must come from whoever prepared the
original: a registrar issuing them, or a quantum memory holding them. A strict check at 32 shots is
$4096 \times 32 = 131{,}072$ SWAP tests, using 131,072 registered 11-qubit states (1,441,792 qubits). Our simulator gets
copies for free by re-preparing from the classical codeword, which is one more reason it holds no advantage.

## 8. State preparation costs about $2^q$ two-qubit gates

A sign state with arbitrary signs is a Hadamard layer followed by a diagonal of $\pm1$ entries. For generic signs the
diagonal is fully entangling, and its two-qubit gate count grows like $2^q$. Transpiled with Qiskit 2.6.1
(`optimization_level=3`, `seed_transpiler=2026`, random odd-weight signs):

| $q$ | 3 | 5 | 7 | 9 | 11 |
|---|---|---|---|---|---|
| all-to-all, basis {cx, rz, sx, x}: two-qubit gates ($= 2^q - 2$ for $q \ge 3$) | 6 | 30 | 126 | 510 | 2046 |
| FakeFez (Heron r2, routed): two-qubit gates | 9 | 40 | 206 | 1003 | 3951 |
| FakeFez depth | 36 | 157 | 740 | 2669 | 10,680 |

A full strict SWAP test ($q = 11$, two preparations plus 11 controlled-SWAPs) is 4167 two-qubit gates all-to-all
(`run_swap_test`). At today's two-qubit error rates, a circuit thousands of gates deep keeps essentially none of the
signal, so full-size fingerprints need fault-tolerant hardware. Noisy and hardware runs use toy fingerprints with $q \le 3$
(`swapprint.toy`); see `docs/README_sections.md` and F6.
**[F6: pending C2: check this table against panel 2 of `experiments/figures/core_noise.png` and its CSV, and use the CSV values if they differ]**

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
