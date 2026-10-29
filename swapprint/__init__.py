"""SwapPrint: detect tampering in digital artwork with quantum fingerprints and SWAP tests.

    import swapprint as sp
    img = sp.load_image("art.png")              # canonical uint8 (256, 256, 3)
    fp = sp.fingerprint(img, "strict")          # one 11-qubit state per 4x4 tile
    cmp = sp.compare(fp, sp.fingerprint(sp.edits.apply(img, "pixel")), shots=32, seed=0)
    cmp.tampered, cmp.flagged                   # True, and which tile changed

The contract (names, shapes, file formats) is docs/CONTRACT.md.
"""

__version__ = "0.2.1"

from . import circuits, config, edits, synthetic, toy
from .compare import Comparison, compare, overlaps
from .fingerprint import Fingerprint, fingerprint, load_fingerprint, save_fingerprint
from .image import load_image
from .theory import code_info, shots_needed

__all__ = [
    "__version__",
    "load_image",
    "fingerprint",
    "Fingerprint",
    "overlaps",
    "compare",
    "Comparison",
    "save_fingerprint",
    "load_fingerprint",
    "code_info",
    "shots_needed",
    "edits",
    "circuits",
    "toy",
    "config",
    "synthetic",
]
