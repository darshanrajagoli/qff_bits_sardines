# Rashida read v1 — frozen final narration

Read only the paragraphs. Leave four seconds of quiet between numbered sections; do not read the headings.

## 01 — hook

This is Hokusai's Great Wave. We changed one pixel, by one shade. Can you see what changed? Neither can anyone. A quantum fingerprint can.

## 02 — idea

Digital art is copied and edited endlessly. SwapPrint gives every four-by-four patch an eleven-qubit quantum fingerprint, built from an error-correcting code, using the published quantum fingerprinting protocol of 2001. A SWAP test compares two fingerprints. In an ideal test, identical patches never read one. A changed patch reads one about half the time.

## 03 — guess

Here's the live app. Somewhere in this image, one pixel moved by one shade. We take a guess, and press Verify.

## 04 — verify

Change detected.

## 05 — shots

These are the SWAP-test shots for the suspicious tile. In a noiseless test, identical states can never give a one And there it is, on shot two.

## 06 — heatmap

The heatmap lands on the exact four-by-four tile. Across held-out paintings, seven shots is the median exact budget for ninety-nine percent detection.

## 07 — frqi

Why does this work? The textbook encoding stores pixels as angles. A one-shade change barely moves that state: its overlap stays at zero point nine nine nine nine nine nine seven and the test sees nothing.

## 08 — bars

For a ninety-nine percent chance of catching this edit, the angle encoding needs about fifteen and a half million shots. SwapPrint needs seven.

## 09 — rigour

We tested it properly. Fifteen artworks. Twenty-two conditions. Sixty-nine thousand three hundred trials. Perceptual thresholds checked on held-out paintings. Qiskit Aer: ninety-seven of one hundred Wilson ninety-five percent intervals contain the exact value. Then real hardware: eighteen toy comparisons on IBM's Marrakesh processor, four thousand shots each. Noise makes even identical states fire. Readout correction helps, but leaves circuit error. These are small toy states, not full-image hardware results.

## 10 — close

To be clear: in practice, a classical S H A two fifty-six hash is the better integrity check today, and full circuits are far beyond current hardware. What SwapPrint shows is how the encoding decides what a quantum measurement can see.

## 11 — end

SwapPrint. By team sardines.
