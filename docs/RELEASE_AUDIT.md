# Saved-result consistency audit

Checked 30 October 2026 against the committed data. This is a recount of saved experiments and an independent classical hash check, not a new QPU run or a claim of final release acceptance.

| Claim | Recount | Scope and source |
|---|---|---|
| Experimental size | 990 pair rows; 69,300 trial rows | 15 artworks, 22 conditions, 3 encodings. Strict 29,700 trials, FRQI 29,700, perceptual 9,900. [Pairs](../experiments/results/tamper_pairs.csv), [trials](../experiments/results/tamper_trials.csv). |
| Strict at 32 shots | 3,120 / 3,120 changed-input trials detected; Wilson 95% 99.877%–100% | Select mode strict, shots=32, n_units_changed > 0 in trials. Excludes controls and no-op edits. Conditional on the tested images/edits and ideal sampler. |
| FRQI at 32 shots | 2,066 / 3,120; 66.22%, Wilson 95% 64.539%–67.857% | Same changed-input selection, mode FRQI. |
| Strict and FRQI unchanged controls | Each 0 / 1,350; Wilson 95% 0%–0.284% | Controls pooled across nine tested budgets, **not** 1,350 controls at 32 shots. |
| Perceptual unchanged controls | 0 / 450; Wilson 95% 0%–0.846% | Controls pooled across three E1 budgets (256, 1024, 4096). This is separate from E3's benign-transformation false-alarm result at 2048 shots. |
| Strict one-channel edit budget | Median 7 shots | 30 exact-budget conditions: six held-out paintings × five pixel cases. This is an exact 99%-detection budget, not an observed guarantee of detection by shot 7 in every trial. [Pair data](../experiments/results/tamper_pairs.csv). |
| Perceptual held-out content detection | 65.14%, 95% artwork-bootstrap interval 59.45%–70.83% | Six held-out paintings, 48 content conditions, 2048 shots, sigma=25, t=0.65. [Calibration JSON](../experiments/results/perceptual_calibration.json). |
| Perceptual held-out benign false alarms | 2.78%, 95% artwork-bootstrap interval 0%–8.33% | Same six paintings, 36 benign conditions. These intervals resample artworks; they are not the pooled-control Wilson intervals above. |
| F7 circuit validation | 97 / 100 intervals cover exact p1; 50 runs per kind | [Aer validation](../experiments/results/core_validation.csv), ancilla and destructive combined. |
| F3 strict overlap / perceptual collisions | Maximum absolute strict overlap .109375; 345 / 26,880 distinct-content region pairs have equal perceptual hashes | Collision rate 1.283%, Wilson 95% 1.156%–1.425%. [F3 CSV](../experiments/figures/collisions.csv). The Gaussian curve is a reference, not a goodness-of-fit certificate. |
| Classical SHA-256 comparison | All 21 changed conditions on Hokusai produced different per-tile digests; unchanged control matched | Reapplied the 22 manifest conditions with the project's edit functions, independently hashed all 4096 RGB tiles with hashlib.sha256 and compared original/candidate digest lists. This does not certify collision freedom. |
| Real hardware | 18 comparison rows, 4,000 counts each; 32 total PUBs; 36 QPU seconds | Count totals and ones/4000 raw probabilities checked in [hardware JSON](../experiments/results/core_hardware.json). Job dbhlpatep8hs73amdun0, ibm_marrakesh; 14 calibration PUBs; q=1–3 toy states only. |

The table's timing values (41.9 / 1.1 / 1.9 / 2.48 ms) are frozen historical fingerprint-generation measurements from [T1](../experiments/figures/baseline_table.csv). This audit did not remeasure timings. Full-image comparison is classically simulated, selected units run on Aer, and F8 is a separate toy hardware experiment.

Data identity (SHA-256):

```text
tamper_pairs.csv              38eef78b89e524a6b8f296f2d8e32d90006cccf30923fcdccf44b9afb877e035
tamper_trials.csv             0e812c600f6b8363ef3b5122c6efd9ae0d7a1e481e9feca12bb509322d58f7b8
core_validation.csv          26e72c6ecfcde00407dc88c96468ae3b1e4f39f5f450a255348b256d4b9cb834
perceptual_calibration.json   032c84ab18f253e32c9e992136f6217a60dda98ac824b778cc5125215ce5718e
```

See the [judge guide](JUDGE_GUIDE.md) and [limitations/Q&A](QA.md).
