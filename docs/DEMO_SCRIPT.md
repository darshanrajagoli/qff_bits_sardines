# SwapPrint: 3-Minute Demo Video Script (Milestone E5)

**Target duration:** 2 minutes 45 seconds (under the 3-minute hard ceiling).  
**Word count:** ~395 words.  
**Cast / Voiceover:** Team Sardines (Problem 5: Quantum Fingerprint).  
**Reproducibility:** Seed pinned to `42` in Verify settings so every measurement trace is deterministic.

---

### Beat 1: The Question (0:00 – 0:10, 10s)
* **Visual:** Browser opens to SwapPrint local Streamlit app at `http://localhost:8501`. Title banner visible.
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
* **Visual:** Set Seed to `42`, shots to `32`. Click **"Verify"**. The banner instantly flashes red: `CHANGE DETECTED`. Scroll to **Heatmap**: a sharp bright spot pinpoints the tampered tile. Click **"▶ Play shots"**: ancilla measurement outcomes stream in real time (magenta `1`s, gray `0`s). A `1` arrives at shot 2.
* **Narration (78 words):**  
  > "We click Verify. A SWAP test compares every tile state against the registered original. Identical states never yield a measurement of one. But because our code spreads any change across half the state, an altered tile yields a one with probability near one-half. Here, with our fixed seed, shot two reads one—conclusive proof of tampering. The heatmap locates the exact 4 by 4 tile without decoding the image."

---

### Beat 5: Compare Encodings — Why Physics Matters (1:20 – 1:45, 25s)
* **Visual:** Scroll to **Compare Encodings** table. Switch sidebar to **"frqi (baseline)"** and click **Verify**. Banner shows green `NO CHANGE DETECTED`.
* **Narration (64 words):**  
  > "Why does encoding matter? Most approaches encode pixels as angles—the textbook FRQI method. On this identical single-pixel edit, FRQI’s quantum overlap stays at 0.9999997. It needs over 15 million shots to detect what SwapPrint catches in just seven. The error-correcting sign encoding makes quantum verification practical."

---

### Beat 6: Rigorous Evaluation & Honest Limits (1:45 – 2:30, 45s)
* **Visual:** Switch to **Tab 5: Results**. Display Figure F2 (shots needed across 22 cases), F3 (1,000,000 collision pairs), and Darshan's Figure F6 (noise on FakeFez).
* **Narration (95 words):**  
  > "We evaluated SwapPrint across 15 artworks and 22 tampering types. Over one million tile pairs confirmed zero false collisions. In perceptual mode, a DCT pHash distinguishes compression from malicious edits. But we are completely honest about limitations: in simulation, SHA-256 is far faster. Full 11-qubit circuits require over 4,000 gates—beyond today's physical hardware without error correction. On noisy IBM devices, environmental noise lifts identical states off zero, requiring calibrated thresholds."

---

### Beat 7: Wrap-up & 20-Second Pitch (2:30 – 2:50, 20s)
* **Visual:** Scroll to top banner; show the downloadable cryptographic verification record PNG.
* **Narration (34 words):**  
  > "SwapPrint proves that thoughtful quantum state encoding turns an impossible millions-of-shots measurement into an immediate 7-shot detection, pinpointing digital edits with rigorous error bounds. Built by Team Sardines for IBM Qiskit Fall Fest 2026."

---

### Automated Storyboard Mapping (`app/demo/storyboard.json`)
The steps above directly map into `app/demo/storyboard.json` for automated 1920×1080 capture with burned-in subtitles via Playwright.
