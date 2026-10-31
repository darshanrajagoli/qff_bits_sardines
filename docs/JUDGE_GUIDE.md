# SwapPrint: a short route through the evidence

Team **sardines** · Problem 5, Quantum Fingerprint · `TEAM-P6GK23`

SwapPrint studies how an encoding changes what the same SWAP test can detect. Start with a tiny artwork edit and its localised tile heatmap, then compare strict code-based fingerprints with perceptual and FRQI encodings. Classical SHA-256 per tile is better in practice; this is an encoding and measurement experiment.

## Try it in 60 seconds

[Open the app](https://qffbitssardines-withoutthes.streamlit.app/) or [watch the 2:59 human-narrated demo](https://drive.google.com/file/d/1MgQzH2eoaSqJfYkz7lAx7c88kPXjNzxP/view). In a fresh app session, keep Hokusai's Great Wave, strict mode, 32 shots per tile and Seed 0. Expand the sidebar if hidden; allow a sleeping deployment a moment to wake.

1. **2 · Tamper → Surprise me:** one pixel changes by one colour level.
2. **3 · Verify → click a guess → Verify:** inspect the verdict, heatmap and flagged 4×4 tile. The guess is part of the game, not an input to the verification calculation.
3. **Compare encodings:** inspect the three encodings on the same edit. The table separates expected shots to the first 1 from the exact budget for 99% detection; those are different quantities.
4. **Run on Qiskit Aer:** separately execute one selected unit as an ancilla or destructive SWAP-test circuit. This is a simulator, not a hardware call.

Full-image Verify samples ideal SWAP-test probabilities computed classically. It does not execute all 4,096 tiles as circuits on a QPU. The real hardware results below are a separate toy-state study. A negative finite-shot verdict means no change was detected, not proof of equality.

## The contribution and the trade-off

**Research question:** with the comparison measurement fixed, how does the encoding change sensitivity to artwork edits? We adapt a published error-correcting-code fingerprint construction to tile localisation and compare it with perceptual and FRQI representations in one reproducible workflow. This is an encoding and measurement experiment, not a newly invented quantum protocol or a secure authentication scheme.

Strict mode spends 11 qubits per fingerprint state to spread small changes across codeword signs; FRQI uses 7 qubits and can make the same edit extremely hard to detect with this measurement. Perceptual mode uses 6 qubits and intentionally tolerates some edits, with measured misses and false alarms. **Fewer shots is not a total-cost or practical-advantage claim:** state preparation, both state registers and the chosen SWAP-test circuit also cost resources. SHA-256 per tile is the better practical integrity check in this setting.

## Follow the rubric to the evidence

| Problem 5 criterion | Points | Where to inspect |
|---|---:|---|
| Fingerprinting design | 30 | [THEORY](THEORY.md): design choices, overlap, localisation and fixed-code heuristic; [code construction](../swapprint/codes.py) → [encodings](../swapprint/encodings.py) → [state preparation and SWAP circuits](../swapprint/circuits.py) |
| Tampering and evaluation | 25 | [saved experiments](../experiments/results/), [figures and CSVs](../experiments/figures/): edited inputs, controls, held-out calibration, detection, collision and localisation studies |
| Encoding and measurement | 20 | [image-fingerprint circuits](../swapprint/circuits.py), [toy-state circuits](../swapprint/toy.py), [F7 Aer validation](../experiments/results/core_validation.csv), [gate costs](../experiments/results/core_gate_costs.csv), [F6 noise](../experiments/results/core_noise.csv), [F8 hardware](../experiments/results/core_hardware.json) |
| Creativity and usability | 15 | [live app](https://qffbitssardines-withoutthes.streamlit.app/): spot-the-edit workflow, heatmap, shot visualisation, circuit comparison and fingerprint registration |
| Limitations and clarity | 10 | [Q&A](QA.md), [THEORY](THEORY.md), [SHA-256 baseline table](../experiments/figures/baseline_table.md), and explicit qualifications below |

## Results to check

- **Encoding changes sensitivity.** For the specified held-out one-channel edits, strict mode's median exact budget for 99% detection is seven shots; FRQI's one-level one-channel calculation needs **15,534,513**. See [F2 data](../experiments/figures/encodings_shots_needed.csv) and [derivation](THEORY.md). These are probability budgets, not a guarantee that every run detects by shot seven.
- **Circuit statistics agree with the exact model at the expected finite-shot scale.** F7 checks 50 pairs per circuit kind, 100 runs total; **97/100** Wilson 95% intervals contain exact probabilities. See [validation data](../experiments/results/core_validation.csv).
- **Noise exposes the gap to hardware.** F8 uses a real **ibm_marrakesh** Heron r2 job, **18 toy comparisons × 4,000 shots**, with **14 shared readout-calibration PUBs**, using **36 QPU seconds**. The tested q=1–3 states are not the full 11-qubit image encoding. Raw counts, calibration and intervals are in [hardware JSON](../experiments/results/core_hardware.json); [F8](../experiments/figures/core_hardware.png) visualises the result.
- **Evaluation includes failure cases and a classical baseline.** At 32 shots, strict detected **3,120/3,120** tested actual-change trials (Wilson 95%: **99.877%–100%**); FRQI detected **2,066/3,120** (**66.22%**, Wilson 95%: **64.539%–67.857%**). Across six held-out paintings, perceptual content detection was **65.14%** (artwork-bootstrap 95%: **59.45%–70.83%**) and benign false alarms were **2.78%** (**0%–8.33%**). These are results on the specified data and edits, not universal performance estimates. The 69,300 E1 trials are repeated simulated measurements across 15 artworks, not 69,300 independent artworks. See the [saved-result audit](RELEASE_AUDIT.md), [calibration](../experiments/results/perceptual_calibration.json) and [SHA-256 comparison](../experiments/figures/baseline_table.md).

## Reproduce the essentials

Use **Python 3.12**, the environment used for our pinned experiments; clone into a short path on Windows. NumPy/SciPy's exact pins require Python 3.12 or newer. From the repository root in a new virtual environment:

```powershell
python -m pip install -r requirements.txt
python -m pip install -r app/requirements.txt
python -m pip install -e .
python examples/quickstart.py
python -m pytest -q -m "not slow"
python -m pytest -q app/tests
python -m experiments.run_tamper --quick
python -m streamlit run app/streamlit_app.py
```

The quick tamper command writes a smoke-test subset into the experiment result paths. Run it in a disposable clone if you want to retain the committed full experiment outputs. Saved data can be inspected without an IBM account; no new hardware job is needed.

## Scope and limitations

The code is public, linear and unkeyed. It is not a digital signature, secure watermark, or practical replacement for SHA-256. Full-image statistics are simulated; Aer runs selected units; F8 is a separate toy hardware study. State preparation is expensive and independent shots require fresh state copies. The fixed-code 30-shot bound is heuristic. Perceptual mode deliberately tolerates small changes and has measured misses/false alarms. Noise can flag unchanged states, so the noiseless single-1 decision rule does not transfer directly to hardware. A negative finite-shot result is not proof that the image is unchanged.

The [saved-result audit](RELEASE_AUDIT.md) recounts headline numerators/denominators and distinguishes the pooled controls from held-out perceptual calibration. The [README](../README.md) gives the complete study, setup, asset credits and contribution details.
