# SwapPrint: judge Q&A

Numbers come from `swapprint` and the CSVs in `experiments/`; the derivations are in `docs/THEORY.md`.
Bold bracketed items are placeholders for results that are still being produced.

## The 20-second pitch

> SwapPrint gives every 4×4 patch of an artwork an 11-qubit quantum fingerprint, using the error-correcting-code
> construction of Buhrman et al. A SWAP test compares fingerprints. Untouched patches never trigger it; a changed patch
> triggers it about half the time, so 30 shots catch an edit with near certainty, and we show where it is. The usual
> "pixels as angles" encoding would need millions of shots for the same edit. Our experiments measure all of this, and
> what IBM-device noise does to small versions of the circuit.

## Questions

**1. Why quantum at all?**
Problem 5 asks for a circuit-based fingerprint and a verification experiment, and the textbook quantum one exists:
Buhrman et al. (2001). We use it to study how encoding and measurement decide what a quantum comparison can detect.
We claim no advantage: our setting is not the model where their advantage holds, and we simulate it classically.

**2. Isn't this just a hash? How does it compare with SHA-256?**
Classically, strict mode is an injective linear code: closer to a checksum than to a cryptographic hash. SHA-256 per
tile catches every changed tile with one comparison and 32 bytes. We need 32 shots per tile, 1 MiB of codeword bits per
image, and fresh state copies per shot. Table T1 puts them side by side.

**3. So why not just use SHA-256?**
In practice you should, and the README says so. SwapPrint is an experiment on encoding and measurement: why one SWAP
test detects a one-pixel edit in a few shots under one encoding and needs millions under another.

**4. Explain the SWAP test.**
Hadamard an ancilla, controlled-SWAP the two registers, Hadamard again, measure: it reads 1 with probability
$(1 - \lvert\langle a|b\rangle\rvert^2)/2$. Equal states never give 1, so a single 1 proves a difference. We also run
the destructive version (Garcia-Escartin & Chamorro-Posada 2013): Bell measurements on the pairs, no ancilla, same $p_1$.

**5. What does the error-correcting code do?**
It spreads any change across the codeword. A one-bit change in a tile flips 955 to 1080 of the 2048 code bits on our
matrix (all 384 cases computed exactly), so the overlap is at most 0.067 in absolute value and $p_1 \ge 0.4977$:
nearly orthogonal states, from the smallest possible edit.

**6. Why does FRQI fail?**
Its overlap is the average of $\cos(\theta_i - \theta'_i)$ over 64 positions. A one-level change moves one angle by
$\pi/510$, so $p_1 = 2.96\times10^{-7}$: on average 3.37 million shots to the first 1, and 15.5 million for 99%
detection. A smooth encoding turns a small edit into a small rotation; a code turns it into a far-away state.

**7. Why 4×4 tiles and 11 qubits?**
A 4×4 RGB tile is 384 bits. A code of length $2^{11}$ gives $p_{1,\min} = 0.371$ (30 shots for a $10^{-6}$ miss), against
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
To ask "did the visible content change?" rather than "did any bit change?". Each 64×64 region becomes a 64-bit DCT
hash on 6 qubits. JPEG re-saves flip few bits and pass; splices and pasted objects flip many and are flagged. Small
edits can pass, by design. Calibration: **[E3: pending: threshold, benign false-alarm rate and content detection rate, with N, from F4]**.

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
It lifts identical pairs off $p_1 = 0$, which breaks the one-sided guarantee: a single 1 no longer proves a change, so
we need a threshold. Measured on FakeFez toy states: **[F6: pending C2: p1 for identical and orthogonal pairs at q = 1–3, both kinds, 4000 shots, with intervals]**.
Over 4096 tiles, a 1% image false-alarm rate needs a per-tile rate of about $2.5\times10^{-6}$ (independence model).

**17. Did you use hardware?**
**[F8: pending C3: either "Yes: toy states (q = 1, 2) on <device>, <date>, job ids in `core_hardware.json`; results next to the noisy-simulator prediction in F8", or "No: noise was simulated on FakeFez; we did not get hardware time."]**
Full-size fingerprints were never run on hardware and cannot be today.

**18. How would it work for real?**
Each shot consumes a copy of both states and unknown states cannot be cloned, so a registrar would issue $k$ copies per
tile (131,072 states for a 32-shot strict check) or hold them in quantum memory. Each state also needs about $2^q$
two-qubit gates to prepare: 2046 all-to-all and 3951 routed on FakeFez at $q = 11$. That is fault-tolerant territory.

**19. What are the limitations?**
No advantage over SHA-256, which is better in practice. The 30-shot bound is heuristic. Fingerprints are public and
decodable, so they are not secret. Noise breaks the one-sided test, full-size circuits are far too deep for today's
hardware, and perceptual mode misses small edits by design. Everything is classically simulated.

**20. What would you do next?**
Run the referee protocol, where Alice and Bob each send a fingerprint and the referee only SWAP-tests, which is the
setting Buhrman et al. analyse. Search our fixed code for low-weight codewords to test the heuristic directly. And
compare cheaper, low-depth state families on hardware.
