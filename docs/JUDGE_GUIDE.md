# SwapPrint: a short route through the evidence

Team **sardines** · Problem 5, Quantum Fingerprint · `TEAM-P6GK23`

SwapPrint studies how an encoding changes what the same SWAP test can detect. Start with a tiny artwork edit and its localised tile heatmap, then compare strict code-based fingerprints with perceptual and FRQI encodings. Classical SHA-256 per tile is better in practice; this is an encoding and measurement experiment.

## Try it

[Open the app](https://qffbitssardines-withoutthes.streamlit.app/). Try the seeded invisible-edit example, inspect the flagged tile and compare encodings. In Verify, a selected unit can be checked using either ancilla or destructive Qiskit Aer circuits. Full-image interaction uses classical evaluation of the same probabilities and finite-shot sampling; it does not execute thousands of tiles on a QPU.

## Follow the rubric to the evidence

| Problem 5 criterion | Points | Where to inspect |
|---|---:|---|
| Fingerprinting design | 30 | [THEORY](THEORY.md): code-to-sign-state mapping, overlap, localisation and fixed-code heuristic; [core implementation](../swapprint/) |
| Tampering and evaluation | 25 | [saved experiments](../experiments/results/), [figures and CSVs](../experiments/figures/): edited inputs, controls, held-out calibration, detection, collision and localisation studies |
| Encoding and measurement | 20 | [circuit implementation](../swapprint/toy.py), [F7 Aer validation](../experiments/results/core_validation.csv), [gate costs](../experiments/results/core_gate_costs.csv), [F6 noise](../experiments/results/core_noise.csv), [F8 hardware](../experiments/results/core_hardware.json) |
| Creativity and usability | 15 | [live app](https://qffbitssardines-withoutthes.streamlit.app/): spot-the-edit workflow, heatmap, shot visualisation, circuit comparison and fingerprint registration |
| Limitations and clarity | 10 | [Q&A](QA.md), [THEORY](THEORY.md), [SHA-256 baseline table](../experiments/figures/baseline_table.md), and explicit qualifications below |

## Three results to check

- **Encoding changes sensitivity.** For the specified held-out one-channel edits, strict mode's median exact budget for 99% detection is seven shots; FRQI's one-level one-channel calculation needs **15,534,513**. See [F2 data](../experiments/figures/encodings_shots_needed.csv) and [derivation](THEORY.md). These are probability budgets, not a guarantee that every run detects by shot seven.
- **Circuit statistics agree with the exact model at the expected finite-shot scale.** F7 checks 50 pairs per circuit kind, 100 runs total; **97/100** Wilson 95% intervals contain exact probabilities. See [validation data](../experiments/results/core_validation.csv).
- **Noise exposes the gap to hardware.** F8 uses a real **ibm_marrakesh** Heron r2 job, **18 toy comparisons × 4,000 shots**, with **14 shared readout-calibration PUBs**, using **36 QPU seconds**. The tested q=1–3 states are not the full 11-qubit image encoding. Raw counts, calibration and intervals are in [hardware JSON](../experiments/results/core_hardware.json); [F8](../experiments/figures/core_hardware.png) visualises the result.

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

The [README](../README.md) gives the complete study, setup, asset credits and contribution details.
