## The app

An interactive Streamlit app on top of the `swapprint` core: fingerprint an artwork, tamper with it, and watch SWAP
tests find the edit.

### Run it

```bash
python -m pip install -r app/requirements.txt          # Streamlit, plotly, the click component, plus swapprint's dependencies
python -m streamlit run app/streamlit_app.py --server.headless true
python -m pytest -q app/tests                          # pinned demo verdicts and the app helpers
```

Then open http://localhost:8501. Use Python 3.12 or 3.13, the same as the core (see Setup above; NumPy 2.5.4 and SciPy 1.18.1 need 3.12+).

### What each tab shows

| Tab | What you do and see |
|---|---|
| **Start here** (above the tabs) | Opens on arrival; collapse it to bring the tabs up. A plain-language guide for someone new to quantum fingerprinting: what the app does, a 60-second walk-through, experiments to try with encoding, shots and seed, a glossary, and links to the papers. |
| **1 · Fingerprint** | The canonical 256×256 image, the numbers behind strict mode (4096 tiles × 11 qubits; 384 bits → 2048-bit codeword → 11-qubit sign state), and a **fingerprint mosaic**: one colour per tile from its codeword. It looks like noise, and an edited tile jumps to a different colour. **Register** downloads the fingerprint as `.npz`. |
| **2 · Tamper** | The original and the edited image sit side by side at the top. Click the edited one to choose a spot, then apply an edit: nudge one pixel by ±1, recolour a pixel, paint a patch, write text, copy-move, splice from another artwork, hide a message in the lowest bits, or change brightness, contrast, JPEG quality or size. Edit history with Undo and Reset, and a download of the edited PNG. **Surprise me** makes a hidden, invisible one-pixel edit for the game; **Challenge a friend** hides your own edits so someone else can play. |
| **3 · Verify** | **Spot the edit:** guess where the hidden edit is, then press Verify. The verdict (`CHANGE DETECTED` / `NO CHANGE DETECTED`; in perceptual mode, `CONTENT CHANGE …`) comes with the number of shots, a **heatmap** of flagged tiles (magenta, colour-blind safe), a zoom on the most suspicious tile, and a **live SWAP test** that plays that tile's shots one by one, with a running estimate of overlap² and a 95% Wilson interval. **Run on Qiskit Aer** builds the real SWAP-test circuit for any tile you click (ancilla or destructive: strict uses 23 qubits or 22, perceptual 13 or 12, FRQI 15 or 14) and shows Aer's estimate next to the exact prediction, plus the hardware-compiled gate count. **Compare encodings** puts the same edit through strict, perceptual and FRQI: a one-pixel edit takes about 2 shots on average to the first 1 in strict mode; 99% detection needs 7 shots, versus 15,534,513 in FRQI. **Check a file** verifies an image against a registered `.npz` without uploading the original (a strict `.npz` can itself reconstruct the canonical image). |
| **How it works** | The five steps (canonical image → tiles → error-correcting code → sign state → SWAP test), the formulas, the 2-qubit SWAP-test circuit, why the encoding matters, and what we don't claim. |
| **Results** | The figures in `experiments/figures/`, exactly as listed in `captions.json` and `core_captions.json`. |

The app uses a pixel-art theme with light and dark modes (switch in the app's ⋮ menu → Settings). Double-click or double-tap any picture to open it full screen.

### How the app computes, said precisely

- **Verify uses the `exact` backend:** each unit's overlap is computed exactly and its SWAP-test outcomes are sampled,
  identical in distribution to a noiseless circuit on that unit. It takes under 2 s.
- **"Run on Qiskit Aer" runs a real circuit** for one tile, in a separate process. The tile is chosen classically (by the
  exact overlap, or by your click), so this is a hybrid demonstration, not a purely quantum verifier.
- **Every number on screen is computed from `swapprint` at runtime**, including the code bound, shot counts, the
  perceptual threshold and the single-bit flip range. None are typed in.
- **A fingerprint is not secret:** a strict `.npz` decodes back to the image, and there is no secret key: anyone can
  fingerprint anything, so a check only shows consistency with a trusted stored reference. It's an integrity check, not
  a signature or watermark. "No change detected" is not proof that nothing changed.

### Third-party code in the app

Streamlit (Apache-2.0), Plotly (MIT), streamlit-image-coordinates (MIT), Pillow (MIT-CMU), Qiskit and Qiskit Aer
(Apache-2.0), Playwright (Apache-2.0, for the scripted demo recording). The artworks are the public-domain images listed
in `data/artworks/SOURCES.md`.

**Design and type.** The app follows the [Carbon Design System](https://carbondesignsystem.com) (Apache-2.0; tokens
from `swapprint/style.py`, CSS in `docs/style/carbon.css`). App type: Departure Mono by Helena Zhang for headings and IBM Plex Mono for text (both SIL Open Font License 1.1; licences in `app/static/fonts/DepartureMono-OFL.txt` and `app/static/fonts/OFL.txt`). SwapPrint is an independent
project by team sardines and is not made or endorsed by IBM.

Screenshots: `app/screenshots/`.
