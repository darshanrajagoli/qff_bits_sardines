# SwapPrint: 3-Minute Demo Video Script (Milestone E5)

**Target duration:** 2 minutes 40 seconds (under the 3-minute hard ceiling).  
**Word count:** ~370 words.  
**Cast / Voiceover:** Team Sardines (Problem 5: Quantum Fingerprint).  
**Reproducibility:** Seed pinned to `42` in Verify settings so every measurement trace is deterministic.

---

### Beat 1: The Question (0:00 – 0:10, 10s)
* **Visual:** Browser opens to SwapPrint local Streamlit app at `http://localhost:8501`. Title banner visible in IBM Carbon styling.
* **Narration (26 words):**  
  > "Can a quantum experiment verify the creative integrity of digital artwork? This is SwapPrint: creative tamper detection using 11-qubit error-correcting states and the SWAP test."

---

### Beat 2: Pick Artwork & Fingerprint Mosaic (0:10 – 0:30, 20s)
* **Visual:** Sidebar selects Hokusai's *The Great Wave*. Switch to **Tab 1: Fingerprint**. The 256×256 image displays beside its 64×64 tile breakdown (4,096 tiles, each 4×4 pixels).
* **Narration (50 words):**  
  > "We canonicalise any artwork to 256 by 256 pixels, divided into 4,096 tiles of 4 by 4 pixels. Passing each tile through a linear code yields a 2,048-bit codeword, mapped directly to the signs of an 11-qubit quantum state. Two identical tiles produce an overlap of exactly one."

---

### Beat 3: "Surprise Me" Invisible Tamper (0:30 – 0:50, 20s)
* **Visual:** Switch to **Tab 2: Tamper**. Click **"Surprise me"**. The tool secretly alters a single pixel by one colour value (`pixel_1` delta +1). Switch to **Tab 3: Verify**.
* **Narration (48 words):**  
  > "Now, someone tampers with the artwork. We click 'Surprise me', which alters just a single pixel by one brightness level. Looking at the two side-by-side images, the change is entirely invisible to the human eye. Can a quantum verification test detect it?"

---

### Beat 4: Verify & Live SWAP-Test Heatmap (0:50 – 1:20, 30s)
* **Visual:** Set Seed to `42`, shots to `32`. Click **"Verify"**. The banner flashes magenta: `CHANGE DETECTED`. Scroll to **Heatmap**: a sharp alert highlight pinpoints the tampered tile. Click **"▶ Play shots"**: ancilla measurement outcomes stream in real time (magenta `1`s, gray `0`s). A `1` arrives at shot 2.
* **Narration (80 words):**  
  > "We click Verify. A SWAP test compares every tile state against the registered original. In the ideal noiseless model, identical inputs have zero probability of producing a one; we flag a tile when a one is observed. A single-bit change flips 955 to 1080 of the 2,048 signs, computed exactly across all 384 input-bit positions. Here, shot two reads one. The alert heatmap locates the flagged 4 by 4 tile without requiring image upload."

---

### Beat 5: Compare Encodings — Why Physics Matters (1:20 – 1:45, 25s)
* **Visual:** Scroll to **Compare Encodings** table. Switch sidebar to **"frqi (baseline)"** and click **Verify**. Banner shows green `NO CHANGE DETECTED`.
* **Narration (68 words):**  
  > "Why does encoding matter? Most approaches encode pixels as angles—the textbook FRQI method. On this identical single-pixel edit, FRQI’s quantum overlap is approximately 0.9999997. It needs over 15 million shots for 99% detection, whereas SwapPrint's strict mode flags it in a median budget of seven shots. The error-correcting sign encoding makes quantum verification practical."

---

### Beat 6: Rigorous Evaluation & Honest Limits (1:45 – 2:30, 45s)
* **Visual:** Switch to **Tab 5: Results**. Display Figure F2 (shots needed across 22 conditions), F3 (1,000,000 collision pairs), and Darshan's Figure F6 (noise on FakeFez).
* **Narration (95 words):**  
  > "We evaluated SwapPrint across 12 museum paintings and three stress images under 22 conditions. Among one million sampled distinct-content strict tile pairs, maximum absolute overlap was 0.1084, supporting our heuristic bound. Perceptual mode detects changes to a coarse DCT hash. But we state all limitations honestly: classical SHA-256 is far faster. Full 11-qubit circuits require over 4,000 gates—beyond today's physical hardware. On a simulated IBM device noise model (FakeFez), noise lifts identical states off zero, requiring calibrated thresholds."

---

### Beat 7: Wrap-up & 20-Second Pitch (2:30 – 2:50, 20s)
* **Visual:** Scroll to top banner; show the downloadable verification record PNG: an unsigned record of this comparison.
* **Narration (36 words):**  
  > "SwapPrint explores how state encoding changes SWAP-test sensitivity and localizes detected edits to tiles. Its general fixed-code miss bound is heuristic, and SHA-256 per tile remains better in practice. Built by Team Sardines for IBM Qiskit Fall Fest 2026."

---

### Automated Storyboard Mapping (`app/demo/storyboard.json`)
The steps above directly map into `app/demo/storyboard.json` and `app/demo/storyboard_cards.json` for automated 1920×1080 capture with burned-in subtitles via Playwright.
