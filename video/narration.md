# SwapPrint: demo video narration (story-first, about 2:35)

Voice: edge-tts `en-US-AndrewNeural`, slightly slowed. Captions show the same words.
Every number is checked against docs/QA.md and the saved CSVs (source in brackets). The collision bound is
heuristic. Image comparisons use the analytical sampler; F6 is simulated device noise, while F8 is a separate
real-QPU measurement of q=1–3 toy states. README integration is by Rashida.

## 1. Hook (0:00–0:15)
**Picture:** the Great Wave fills the frame on Carbon g100, a slow eased push-in. A magnifier finds one pixel; its
green value ticks from 89 to 88 (the real seeded edit, pixel 206, 158). Then the title: **SwapPrint**, "Quantum
fingerprints for digital art".

> This is Hokusai's Great Wave. We changed one pixel, by one shade. Can you see what changed? Neither can anyone.
> A quantum fingerprint can.

## 2. Stakes and idea (about 20 s)
**Picture:** an animated diagram, no paragraphs. The artwork splits into a 64 × 64 grid; one 4 × 4 tile lifts out;
its bits run through a code into a 2,048-sign codeword; the codeword becomes an 11-qubit state |ψ⟩; two states feed a
SWAP-test circuit that draws itself (H, controlled-SWAP, H, measure).

> Digital art is copied and edited endlessly. SwapPrint gives every four-by-four patch an eleven-qubit quantum
> fingerprint, built from an error-correcting code, after Buhrman and colleagues in 2001. A SWAP test compares two
> fingerprints. In an ideal test, identical patches never read one. A changed patch reads one about half the time.

[README "Design"; 4,096 tiles, [2048, 384] code, q = 11; p1 = (1 − overlap²)/2 ≈ 0.5 for a changed tile]

## 3. Magic moment (about 35 s)
**Picture:** the live app. Spot-the-edit: our guess lands far from the truth. Verify. The verdict. The live SWAP-test
shots stream in; the first magenta "1" lands on shot 2 and is outlined. Then the heatmap, and an eased zoom onto the
exact 4 × 4 tile.

> Here's the live app. Somewhere in this image, one pixel moved by one shade. We take a guess, and press Verify.
> Change detected. These are the SWAP-test shots for the suspicious tile. In a noiseless test, identical states can
> never give a one. And there it is, on shot two. The heatmap lands on the exact four-by-four tile. Across held-out
> paintings, seven shots is the median exact budget for ninety-nine percent detection.

[first 1 on shot 2: video/out/raw/facts.json at seed 0; median 7 shots: README T1 "median 7 shots"]

## 4. Why the encoding matters (about 25 s)
**Picture:** the app switches to FRQI: "NO CHANGE DETECTED". Then a full-frame Carbon chart, log scale: the strict
bar stops at 7 shots; the FRQI bar keeps climbing, the counter racing to 15.5 million.

> Why does this work? The textbook encoding stores pixels as angles. A one-shade change barely moves that state: its
> overlap stays at 0.9999997, and the test sees nothing. For a 99 percent chance of catching this edit, the angle
> encoding needs about 15.5 million shots. SwapPrint needs seven.

[README: FRQI ≈ 15.5 million shots, p1 = 2.96 × 10⁻⁷; strict 7; facts.json: frqi_99 = 15,534,513, strict_99 = 7]

## 5. Rigour (about 35 s)
**Picture:** quick cuts of the saved experiment, calibration, Aer and F8 hardware figures on Carbon cards.

> We tested it properly. Fifteen artworks. Twenty-two conditions. Sixty-nine thousand three hundred trials.
> Perceptual thresholds checked on held-out paintings. Qiskit Aer: ninety-seven of one hundred Wilson ninety-five
> percent intervals contain the exact value. Then real hardware: eighteen toy comparisons on IBM's Marrakesh
> processor, four thousand shots each. Noise makes even identical states fire. Readout correction helps, but leaves
> circuit error. These are small toy states, not full-image hardware results.

[tamper_trials.csv: 69,300 rows; six held-out paintings; core_validation.csv: 97/100 Wilson intervals;
core_hardware.json: ibm_marrakesh, job dbhlpatep8hs73amdun0, 18 comparisons at 4000 shots plus 14 calibration PUBs,
36 QPU seconds. Conditional bootstrap intervals and raw counts are retained in F8's CSV/JSON.]

## 6. Honest close (about 20 s)
**Picture:** back to the verdict and heatmap, slow push-in; end card.

> To be clear: in practice, a classical SHA-256 hash is the better integrity check today, and full circuits are far
> beyond current hardware. What SwapPrint shows is how the encoding decides what a quantum measurement can see.
> SwapPrint. By team sardines.

End card: **SwapPrint · team sardines** · github.com/darshanrajagoli/qff_bits_sardines · IBM Qiskit Fall Fest 2026
hackathon · Built with Qiskit · credits (Carbon Apache-2.0, IBM Plex OFL 1.1, synthetic narration, music if any;
"an independent project, not made or endorsed by IBM").
