"""Run one SWAP-test circuit on Qiskit Aer in its own process, so a native crash can never take down the app.

    python app/aer_worker.py fp_a.npz fp_b.npz UNIT SHOTS KIND SEED   ->  prints run_swap_test's dict as JSON
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import swapprint as sp  # noqa: E402


def main() -> None:
    path_a, path_b, unit, shots, kind, seed = sys.argv[1:7]
    res = sp.circuits.run_swap_test(sp.load_fingerprint(path_a), sp.load_fingerprint(path_b), int(unit),
                                    shots=int(shots), kind=kind, seed=int(seed))
    print(json.dumps({k: (float(v) if isinstance(v, float) else int(v)) for k, v in res.items()}))


if __name__ == "__main__":
    main()
