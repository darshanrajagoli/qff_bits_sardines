# Table T1: Classical vs. Quantum Fingerprinting Baseline Comparison

*Benchmarked on 13th Gen Intel(R) Core(TM) i5-13420H (Windows 11). Canonical image size: 256×256 RGB (192 KiB). Dataset: 22 conditions (21 tampering edits + 1 unchanged control).* 

| Method / Mode | Unit / Tile | Qubits | Detects 1-Pixel? | Image Detection (Budget) | False Alarm | Storage per Image | Comparisons | Fingerprint-generation time | Practicality / Hardware Note |
|---|---|---|---|---|---|---|---|---|---|
| **Strict Mode (SwapPrint)** | 4x4 px (4096 tiles) | 11 | Yes (median 7-shot budget for 99% detection) | 3,120/3,120 actual changes detected (100.00%, 95% Wilson: 99.88%–100%) | 0/1,350 observed on unchanged controls pooled across 9 budgets (0.00%, 95% Wilson: 0%–0.284%); ideal false alarm exactly zero | 1 MiB packed (8 MiB uint8; 1025.9 KiB .npz) | 4,096 x 32 = 131,072 SWAP tests | 41.9 ms | Requires ~4,180 2-qubit gates per tile; beyond NISQ capabilities |
| **Perceptual Mode (SwapPrint)** | 64x64 px (16 regions) | 6 | No (deliberately ignored) | 65.14% content (100% on splices/patches; 2.78% benign FA at 2048 shots) | 0/450 observed on unchanged controls pooled across 3 budgets (0.00%, 95% Wilson: 0%–0.846%); separate from benign FA (2.78% at 2048 shots) | 128 B packed (1 KiB uint8 array; 1.8 KiB .npz) | 16 x 2048 = 32,768 SWAP tests | 1.1 ms | Hardware performance at this size was not established; noise experiments use toy states with q≤3 |
| **FRQI Baseline (Pixels as Angles)** | 4x4 px (4096 tiles) | 7 | No at 32 shots (needs 15,534,513 shots for 99% detection) | 2,066/3,120 actual changes detected (66.22%, 95% Wilson: 64.54%–67.86%) | 0/1,350 observed on unchanged controls pooled across 9 budgets (0.00%, 95% Wilson: 0%–0.284%) | 2 MiB (float64; 260.8 KiB .npz) | 4,096 x 32 = 131,072 SWAP tests | 1.9 ms | Uniformly controlled RY gates, deep decomposition |
| **Classical Baseline: SHA-256 per Tile** | 4x4 px (4096 tiles) | 0 (Classical) | Yes (1 comparison) | 100.0% (all 21 tested non-control edits produced different digests) | 0.00% (deterministic equality) | 128 KiB (4096 x 32 B hashes) | 4,096 classical 32-byte equality checks | 2.48 ms | SHA-256 per tile is better in practice; runs natively on CPU |

### Key Takeaways
- **SHA-256 per tile is better in practice**: The saved benchmark records 2.48 ms for digest generation and 128 KiB of digests. All 21 tested non-control edits on one artwork produced different digests in deterministic checks; this does not certify collision freedom.
- **The quantum contribution is the encoding and measurement study**: For the tested one-channel edits, the median exact budget for 99% detection across six held-out paintings is seven shots in strict mode, whereas textbook FRQI requires 15,534,513 shots.
- **Honest limits**: Full 11-qubit circuits require ~4,180 two-qubit gates all-to-all and 10,129 on FakeFez, which exceeds current NISQ hardware limits without error mitigation or fault tolerance.
