# SwapPrint core contract (v0.2)

Everything that crosses a folder boundary is defined here: function names, inputs, outputs, file formats.
Change it only after agreeing the change with the team, and bump `swapprint.__version__`.

## Folders and owners

| Path | Owner | Contents |
|---|---|---|
| `swapprint/` | Darshan | the quantum core library (everything except `edits.py`) |
| `swapprint/edits.py` | Rashida | image edits, shared by the app and the experiments |
| `tests/` | Darshan | pytest suite |
| `app/` | Ansh | Streamlit app, entry point `app/streamlit_app.py` |
| `experiments/` | Rashida | tamper experiments; `experiments/results/*.csv`, `experiments/figures/*.png` |
| `data/artworks/` | Rashida | canonical 256×256 PNG artworks and `data/artworks/SOURCES.md` (source URL and licence per image) |
| `docs/` | Darshan | `CONTRACT.md` (this file), `THEORY.md`, `QA.md` |
| `README.md` | Rashida | the submission README; others send her their sections |

Edit only your own paths. To change someone else's, ask its owner first.

## Fixed parameters (`swapprint/config.py`)

| Name | Value | Meaning |
|---|---|---|
| `CANON` | 256 | canonical image is 256×256 RGB |
| `STRICT_TILE` | 4 | strict mode works on 4×4-pixel tiles: a 64×64 grid, 4096 tiles |
| `STRICT_BITS` | 384 | bits per tile (4·4 pixels · 3 channels · 8 bits) |
| `STRICT_Q` | 11 | qubits per strict fingerprint; code length m = 2¹¹ = 2048 |
| `CODE_SEED` | `"qff-sardines-2026"` | public seed of the error-correcting code |
| `PERCEPTUAL_REGION` | 64 | perceptual mode works on 64×64-pixel regions: a 4×4 grid, 16 regions |
| `PERCEPTUAL_Q` | 6 | qubits per perceptual fingerprint (64 hash bits) |
| `PERCEPTUAL_F_THRESHOLD` | 0.65 (E3) | a region is flagged if its estimated F = overlap² is below this, i.e. 10 or more of its 64 hash bits changed (textured regions always hash to weight 31, so distances are even). Starting value from four Met paintings; recalibrated on held-out artworks (Rashida, E3), then fixed here (Darshan) |
| `PHASH_FLAT_SIGMA` | 25.0 | a region whose AC RMS (63 low-frequency DCT coefficients) is below this counts as flat: all its hash bits are 0 |
| `PERCEPTUAL_SHOTS` | 2048 (E3) | `compare`'s default shots in perceptual mode: it estimates F against a threshold, so it needs many shots |
| `DEFAULT_SHOTS` | 32 | `compare`'s default shots in strict and frqi mode: a single 1 decides, and 30 shots already give a 10⁻⁶ miss bound |

## The three encodings

Every encoding turns one unit of the image into a quantum state. Two states are compared with a SWAP test, whose
ancilla reads 1 with probability **p1 = (1 − overlap²) / 2**. Identical states give p1 = 0, so a single 1 proves the
inputs differ. Orthogonal states give p1 = ½.

| Mode | Unit | Input per unit | State | Qubits | Overlap | Meant to detect |
|---|---|---|---|---|---|---|
| `strict` | 4×4 tile | 384 bits x | (1/√2048) Σᵢ (−1)^E(x)ᵢ \|i⟩, where E is a pseudo-random linear [2048, 384] code | 11 | 1 − 2·d(E(x), E(y))/2048 | any change at all, even one bit |
| `perceptual` | 64×64 region | 64-bit DCT hash b (pHash: region averaged down to 32×32, the 63 lowest-frequency AC coefficients vs their median, plus a fixed padding bit; flat regions hash to all zeros) | (1/8) Σᵢ (−1)^bᵢ \|i⟩ | 6 | 1 − 2·d(b, b′)/64 | visible content changes, while tolerating re-saves; it deliberately ignores tiny edits, which strict mode catches |
| `frqi` (baseline) | 4×4 tile | 48 channel values v in positions 0–47; positions 48–63 padded with θ = 0 | FRQI: (1/8) Σᵢ (cos θᵢ\|0⟩ + sin θᵢ\|1⟩)\|i⟩, θ = (π/2)·v/255, prepared by Hadamards on the 6 position qubits and uniformly controlled RY(2θᵢ) on the colour qubit | 6 + 1 | mean over the 64 positions of cos(θᵢ − θ′ᵢ) | the "pixels as angles" approach, which barely detects small edits |

d(·,·) is Hamming distance. `strict` follows the construction of Buhrman, Cleve, Watrous and de Wolf (2001), with
sign phases in place of an extra qubit. Because the code is linear, overlap depends only on x ⊕ y.
`frqi` is the baseline we beat. FRQI (Le, Dong, Hirota 2011) is a standard way of putting images into qubits. A
one-level edit of one value moves its overlap by only about 3×10⁻⁷, so the SWAP test needs millions of shots to
notice.

## API (`import swapprint as sp`)

```python
img = sp.load_image(src)          # src: path | bytes | PIL.Image | ndarray. Returns uint8 (256, 256, 3).
fp  = sp.fingerprint(img, mode)   # mode: "strict" | "perceptual" | "frqi". Returns Fingerprint.
ov  = sp.overlaps(fp_a, fp_b)     # exact overlap per unit, float64 array of shape fp.grid
cmp = sp.compare(fp_a, fp_b, shots=None, backend="exact", seed=None, threshold=None, trace_tiles=4, kind="ancilla")
                                  # shots=None: 32 for strict/frqi, PERCEPTUAL_SHOTS for perceptual
sp.save_fingerprint(fp, path)     # .npz
fp  = sp.load_fingerprint(path)
info = sp.code_info()             # dict: n, m, rate, seed, d_min_guaranteed, overlap_max, p1_min, failure_prob
k   = sp.shots_needed(miss=1e-6, p1=info["p1_min"])
bits = sp.encodings.perceptual(img, flat_sigma=None)  # (16, 64) hash bits; flat_sigma overrides PHASH_FLAT_SIGMA for sweeps
```

`load_image` is deterministic on every machine. It applies EXIF transpose, converts to RGB, then resizes with
integer-only box averaging written in numpy, with no Pillow resampling. A 256×256 input passes through unchanged.
A non-square input is **stretched**, not cropped: centre-crop it first if the aspect ratio matters (the gallery does).

### `Fingerprint` (frozen dataclass)

| Field | Type | Meaning |
|---|---|---|
| `mode` | str | `"strict"`, `"perceptual"` or `"frqi"` |
| `q` | int | qubits per unit state (11, 6 or 7) |
| `grid` | (int, int) | (rows, cols) of units: (64, 64) for strict and frqi, (4, 4) for perceptual |
| `unit_px` | int | unit side in canonical pixels: 4 or 64 |
| `data` | ndarray | strict: codewords (4096, 2048) uint8 0/1; perceptual: hash bits (16, 64) uint8 0/1; frqi: angles (4096, 64) float64, last 16 are padding zeros |
| `version` | str | e.g. `"swapprint-0.1/strict/q11/qff-sardines-2026"`. `compare` refuses mismatched versions. |

### `Comparison` (dataclass, `to_dict()` gives JSON-safe output)

| Field | Type | Meaning |
|---|---|---|
| `mode`, `backend`, `shots` | | as requested |
| `grid` | (int, int) | as in the fingerprints |
| `overlap` | float array, grid | exact overlap per unit |
| `p1` | float array, grid | (1 − overlap²)/2 |
| `ones` | int array, grid | number of shots that read 1 |
| `flagged` | bool array, grid | unit judged changed |
| `tampered` | bool | overall verdict |
| `changed_fraction` | float | flagged units / all units |
| `traces` | dict[int, list[int]] | per-shot outcomes (0/1) for the `trace_tiles` most suspicious units, used for the shot-by-shot animation; `ones` agrees with them |
| `first_detection` | dict[int, int or None] | 1-based shot index of the first 1 for each traced unit |
| `circuit_tiles` | list[int] | units that were run as real Qiskit circuits (empty for `exact`) |
| `miss_bound` | float or None | only for strict mode with the default any-1 rule (no `threshold`): (1 − p1_min)^shots, a heuristic upper bound on P(no detection \| a tile changed). It is **not** the probability that the image is unchanged. None otherwise. |

Unit index = row · cols + col, row-major.

### Decision rule

* `strict`, `frqi`: a unit is flagged if `ones > 0`. A noiseless SWAP test never reads 1 on identical inputs. With a
  noisy backend, pass `threshold`: a unit is flagged if `ones / shots > threshold`.
* `perceptual`: estimate F̂ = max(0, 1 − 2·ones/shots); a unit is flagged if F̂ < `threshold`, which defaults to
  `PERCEPTUAL_F_THRESHOLD`.
* `tampered` is true if any unit is flagged.

### Backends

| `backend` | Status | What runs |
|---|---|---|
| `"exact"` | in v0.1 | exact SWAP-test statistics: p1 from the exact overlap, outcomes sampled with numpy. Identical in distribution to a noiseless circuit. |
| `"aer"` | milestone C1 | as `exact`, but the traced units run as real SWAP-test circuits on Qiskit Aer (per-shot outcomes in `traces`); they are listed in `circuit_tiles`. Optional `kind="ancilla"\|"destructive"` |
| `"aer-noisy:<FakeBackend>"` | milestone C2 | only for small "toy" fingerprints, through `sp.toy.run(...)`, because full-size circuits are far too deep for today's hardware |
| `"ibm:<device>"` | milestone C3 | toy fingerprints on a real IBM device, with a mentor's approval |

### Circuits (`swapprint/circuits.py`, milestone C1)

```python
qc = sp.circuits.state_circuit(fp, unit)                        # prepares the unit's state on fp.q qubits
qc = sp.circuits.swap_test(fp_a, fp_b, unit, kind="ancilla")    # 2q+1 qubits; kind="destructive": 2q qubits, Bell-basis
res = sp.circuits.run_swap_test(fp_a, fp_b, unit, shots=1024, backend="aer", kind="ancilla")
# res: {"ones", "shots", "p1_est", "p1_exact", "qubits", "two_qubit_gates", "depth", "seconds"}
qc = sp.circuits.example_circuit(q=2, kind="ancilla")           # a small SWAP test for the app to draw
```

`python -m swapprint.validate` checks the exact statistics against Aer and writes `experiments/results/core_validation.csv`.
Toy runs (`swapprint/toy.py`): `sp.toy.run(q, pair="same"|"orthogonal"|"near", shots=4000, backend=..., kind=...) -> dict`.

## Image edits (`swapprint/edits.py`, owner Rashida)

Each edit takes a canonical image and returns a new canonical image, without modifying its input:

```python
sp.edits.REGISTRY: dict[str, Edit]   # Edit(fn, defaults: dict, category: str)
new = sp.edits.apply(img, "patch", y=40, x=60, size=5)
```

| Category | Edits |
|---|---|
| `control` | `identity` |
| `imperceptible` | `pixel` (one channel of one pixel ±1), `lsb` (hide a message in least significant bits) |
| `benign` | `jpeg`, `brightness`, `contrast`, `resize_roundtrip` |
| `content` | `set_pixel`, `patch`, `copy_move`, `splice`, `text` |
| `different` | an unrelated artwork, used as the collision test |

## File formats

* `experiments/manifest.json`: the frozen experiment design (artworks with their split, cases with full parameters).
* `experiments/results/tamper_pairs.csv`, one row per (artwork, case, mode), exact probabilities, no sampling:
  `artwork, split, case_id, category, mode, n_units, n_units_changed, overlap_min, p1_max, p_detect_k<k>..., shots_99_image, recall`
  (`shots_99_image` is an integer, `never` or `>16384`)
* `experiments/results/tamper_trials.csv`, one row per sampled trial:
  `artwork, split, case_id, category, mode, shots, rep, n_units_changed, n_flagged, n_flagged_changed, detected`
* Files written by the core (C1, C2) use the `core_` prefix: `experiments/results/core_*.csv`.
* Figures: `experiments/figures/<name>.png` at 200 dpi, plus a matching `.csv` holding the plotted numbers.
* Registered fingerprints: `.npz` written by `save_fingerprint`. Strict codewords are stored bit-packed.
