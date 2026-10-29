"""Render the 2-qubit SWAP-test drawings the app shows (run once; the PNGs are committed).

    python app/make_assets.py

The app never builds Qiskit circuits in its own process: Qiskit crashed when circuits were built on later Streamlit
rerun threads, so circuits run in app/aer_worker.py and the drawings are pre-rendered here.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import swapprint as sp  # noqa: E402

OUT = Path(__file__).resolve().parent / "assets"

for kind in ("ancilla", "destructive"):
    fig = sp.circuits.example_circuit(q=2, kind=kind).draw("mpl", fold=-1, style="iqp-dark")
    fig.savefig(OUT / f"swap_test_q2_{kind}.png", dpi=160, bbox_inches="tight", transparent=True)
    print("wrote", OUT / f"swap_test_q2_{kind}.png")
