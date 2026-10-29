"""Fixed parameters of SwapPrint v0.3 (the table in docs/CONTRACT.md).

Every fingerprint depends on these values, so changing one changes every fingerprint: agree the change with the
team and bump `swapprint.__version__` first.
"""

CANON = 256  # the canonical image is CANON x CANON RGB
STRICT_TILE = 4  # strict mode works on 4x4-pixel tiles: a 64x64 grid, 4096 tiles
STRICT_BITS = 384  # bits per tile: 4*4 pixels * 3 channels * 8 bits
STRICT_Q = 11  # qubits per strict fingerprint; code length m = 2**11 = 2048
CODE_SEED = "qff-sardines-2026"  # public seed of the error-correcting code
PERCEPTUAL_REGION = 64  # perceptual mode works on 64x64-pixel regions: a 4x4 grid, 16 regions
PERCEPTUAL_Q = 6  # qubits per perceptual fingerprint (64 hash bits)
PERCEPTUAL_RULE = "median"  # v0.2 default; deadzone is an explicit ablation option
PERCEPTUAL_F_THRESHOLD = 0.65  # E3: experiments/calibrate_perceptual.py
PHASH_AC_FLOOR = 10.0  # ablation only: experiments/core_perceptual_v3.py
PHASH_FLAT_SIGMA = 25.0  # default median-rule AC RMS cutoff (v0.2)
PERCEPTUAL_SHOTS = 2048  # E3; compare() estimates F against a threshold
DEFAULT_SHOTS = 32  # compare()'s default budget in strict and frqi mode; 30 already gives a 1e-6 miss bound

# Derived values, not free parameters.
STRICT_M = 2**STRICT_Q  # 2048 code bits, one sign per amplitude of the strict state
STRICT_GRID = CANON // STRICT_TILE  # 64 tiles per side
PERCEPTUAL_BITS = 2**PERCEPTUAL_Q  # 64 hash bits, one sign per amplitude of the perceptual state
PERCEPTUAL_GRID = CANON // PERCEPTUAL_REGION  # 4 regions per side
FRQI_VALUES = STRICT_TILE * STRICT_TILE * 3  # 48 channel values per tile
FRQI_Q = 7  # 6 position qubits (64 >= 48 slots) + 1 colour qubit
FRQI_POSITIONS = 2 ** (FRQI_Q - 1)  # 64 positions; the last 16 have theta = 0 in every image

assert STRICT_BITS == FRQI_VALUES * 8
