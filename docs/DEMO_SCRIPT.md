# SwapPrint: 3-Minute Demo Video Script (Milestone E5)

**Target duration:** 2 minutes 45 seconds (under the 3-minute hard ceiling).  
**Word count:** ~210 spoken words (paced comfortably with title and section cards).  
**Cast / Voiceover:** Team Sardines (Problem 5: Quantum Fingerprint).  
**Recording Pipeline:** Fully automated via `python app/demo/record_demo.py app/demo/storyboard_cards.json` (1920×1080, IBM Carbon title/section/end cards, IBM Plex captions).  
**Reproducibility:** Seed pinned to `42` in Verify settings so every measurement trace is deterministic.

---

### Beat 1: Title Card & The Question (0:00 – 0:15, 15s)
* **Visual:** Carbon title card: *SwapPrint · Quantum fingerprints for digital art · team sardines · Qiskit Fall Fest 2026*. Transitions to local/public app showing Hokusai's *Under the Wave off Kanagawa*. Switch to **Tab 1: Fingerprint** showing canonical 256×256 image and 64×64 tile breakdown.
* **Narration:**  
  > "SwapPrint: quantum fingerprints for digital art. We start with Hokusai's Great Wave. Every 4x4 patch gets its own 11-qubit fingerprint state."

---

### Beat 2: Section Card: Tamper & Invisible Edit (0:15 – 0:40, 25s)
* **Visual:** Carbon section card: *Tamper*. Switch to **Tab 2: Tamper**. Click **"Surprise me"** (or use **"Challenge a friend"**). A secret 1-pixel edit is applied at coordinate $(x=154, y=202)$. Switch to **Tab 3: Verify**.
* **Narration:**  
  > "Now someone quietly edits the artwork: one pixel, one colour level. Surprise me hides a single invisible edit somewhere in the image. Can you spot the edit? Nobody can by eye. Let's guess: click where we think the change is."

---

### Beat 3: Verify, Live SWAP Test & Qiskit Aer (0:40 – 1:30, 50s)
* **Visual:** Click **"Verify"**. Banner flashes magenta: `CHANGE DETECTED`. Heatmap highlights the tampered 4×4 tile at $(154, 202)$. Click **"▶ Play shots"**: ancilla measurement outcomes stream in real time (gray `0`s, magenta `1`s). Click **"Run on Qiskit Aer"**: executes a real 23-qubit circuit in a child process; simulator output matches exact theoretical $p_1$.
* **Narration:**  
  > "Press Verify: the SWAP test compares every fingerprint, tile by tile. CHANGE DETECTED. The heatmap points straight at the edited tile. Untouched tiles never fire. A changed tile fires about half the time. Watch the SWAP test shots arrive one by one: grey is 0, magenta is 1. The same test, as a real circuit on Qiskit's Aer simulator. Aer agrees with the exact answer."

---

### Beat 4: Compare Encodings — Why Physics Matters (1:30 – 2:05, 35s)
* **Visual:** Scroll to **Compare Encodings**. Switch sidebar radio to **"frqi (baseline)"**. Click **Verify**. Banner shows green `NO CHANGE DETECTED`.
* **Narration:**  
  > "Why the encoding matters: same edit, same SWAP test, three encodings. Switch to the textbook baseline encoding, FRQI. Verify again with FRQI... NO CHANGE DETECTED. FRQI needs millions of shots to notice this edit. Same SWAP test, different encoding: 99% detection takes 15.5 million shots with FRQI, 7 with ours."

---

### Beat 5: How It Works & Rigorous Evaluation (2:05 – 2:30, 25s)
* **Visual:** Switch to **Tab: How it works** (shows 5-step pipeline diagram and mathematical formulations). Carbon section card: *Results*. Switch to **Tab: Results** (displays Figures F1–F5 and noise study F6).
* **Narration:**  
  > "How: tile, error-correcting code, 11-qubit sign state, SWAP test. One flipped bit flips about half the signs. Measured, not assumed: 12 paintings, 3 stress images, 22 conditions, Wilson 95% intervals on sampled rates."

---

### Beat 6: Honest Limits & SHA-256 Baseline (2:30 – 2:45, 15s)
* **Visual:** Scroll to **Circuits and noise** section of Results tab. Return to **Tab 3: Verify** showing the downloadable unsigned verification record PNG. Carbon end card: credits for Carbon Design System (Apache-2.0) and IBM Plex (SIL OFL 1.1).
* **Narration:**  
  > "Honest limit: on a simulated IBM device noise model (FakeFez), identical states start to fire, so real devices need thresholds. SHA-256 is still better in practice. What SwapPrint shows: the encoding decides what a SWAP test can see."

---

### Automated Storyboard Sync
The script above is synchronized with:
- `app/demo/storyboard.json` (clean run with Plex captions)
- `app/demo/storyboard_cards.json` (broadcast run with Carbon title, section, and end cards)
- Command to reproduce: `python app/demo/record_demo.py app/demo/storyboard_cards.json --url=http://localhost:8501 --out=demo_v2`
