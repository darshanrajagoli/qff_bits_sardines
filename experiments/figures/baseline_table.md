# Table T1: Classical vs. Quantum Fingerprinting Baseline Comparison

*Benchmarked on 13th Gen Intel(R) Core(TM) i5-13420H (Windows 11). Canonical image size: 256×256 RGB (192 KiB).* 

| Method / Mode | Unit / Tile | Qubits | Detects 1-Pixel? | Image Detection (Budget) | False Alarm | Storage per Image | Comparisons | Wall Time | Practicality / Hardware Note |
|---|---|---|---|---|---|---|---|---|---|
| **Strict Mode (SwapPrint)** | 4x4 px (4096 tiles) | 11 | Yes (median 7 shots) | 100.0% (any tile change) | 0.00% (noiseless, Wilson <= 0.05%) | 1 MiB packed (8 MiB uint8; 1025.9 KiB .npz) | 4,096 x 32 = 131,072 SWAP tests | 54.0 ms | Requires ~4,180 2-qubit gates per tile (simulated on Aer) |
| **Perceptual Mode (SwapPrint)** | 64x64 px (16 regions) | 6 | No (deliberately ignored) | 0.0% (calibrated budget 2048 shots: 65.1% content, 2.8% benign) | 0.00% | 128 B (64 B packed; 1.8 KiB .npz) | 16 x 2048 = 32,768 SWAP tests | 1.8 ms | 6 qubits, shallower state prep (~120 gates) |
| **FRQI Baseline (Pixels as Angles)** | 4x4 px (4096 tiles) | 7 | No at 32 shots (needs ~15.5M shots) | 0.0% on subtle edits; catches large patches | 0.00% | 2 MiB (float64; 260.8 KiB .npz) | 4,096 x 32 = 131,072 SWAP tests | 1.8 ms | Uniformly controlled RY gates, deep decomposition |
| **Classical Baseline: SHA-256 per Tile** | 4x4 px (4096 tiles) | 0 (Classical) | Yes (1 comparison) | 100.0% (21/21 edits detected) | 0.00% (zero collisions in history) | 128 KiB (4096 x 32 B hashes) | 4,096 classical 32-byte equality checks | 5.82 ms | Runs on any CPU in microseconds; wins on practicality |

### Key Takeaways
- **SHA-256 wins decisively on practicality**: It detects every changed tile in under 3 milliseconds with 128 KiB storage, zero false alarms, and zero collisions.
- **The quantum contribution is the encoding and measurement study**: Strict mode with Buhrman et al.'s error-correcting sign-state construction detects a one-pixel edit in just 7 shots (median), whereas textbook FRQI requires ~15.5 million shots.
- **Honest limits**: Full 11-qubit circuits require ~4,180 two-qubit gates, which exceeds current NISQ hardware limits without error mitigation or fault tolerance.
