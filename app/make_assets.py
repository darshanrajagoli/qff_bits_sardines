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
from swapprint import style  # noqa: E402

OUT = Path(__file__).resolve().parent / "assets"

style.use("g100")  # IBM Plex + Carbon g100 greys for matplotlib
t = style.tokens("g100")
CIRCUIT_STYLE = {  # Carbon g100: purple accent for the SWAP-test gates, greys for everything else
    "backgroundcolor": t["background"], "textcolor": t["text-primary"], "subtextcolor": t["text-secondary"],
    "linecolor": t["text-secondary"], "creglinecolor": t["text-helper"], "gatetextcolor": "#ffffff",
    "fontsize": 13, "subfontsize": 9,
    "displaycolor": {
        "h": [style.PURPLE, "#ffffff"], "cswap": [style.ACCENT_ON_DARK, "#ffffff"],
        "swap": [style.ACCENT_ON_DARK, "#ffffff"], "diagonal": [t["layer-02"], "#ffffff"],
        "measure": [t["layer-02"], "#ffffff"], "cx": [style.ACCENT_ON_DARK, "#ffffff"],
        "z": [t["layer-02"], "#ffffff"], "cz": [style.ACCENT_ON_DARK, "#ffffff"],
    },
}

for kind in ("ancilla", "destructive"):
    fig = sp.circuits.example_circuit(q=2, kind=kind).draw("mpl", fold=-1, style=CIRCUIT_STYLE)
    fig.savefig(OUT / f"swap_test_q2_{kind}.png", dpi=160, bbox_inches="tight", facecolor=t["background"])
    print("wrote", OUT / f"swap_test_q2_{kind}.png")
