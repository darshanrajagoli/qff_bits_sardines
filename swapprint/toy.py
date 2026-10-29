"""Toy fingerprints for Aer (C1), noisy simulators (C2) and IBM hardware (C3). Stub in v0.1.

Full-size fingerprints need circuits far too deep for today's devices, so hardware runs use a pair of q-qubit sign
states that are either identical (ideal p1 = 0) or orthogonal (ideal p1 = 1/2). Qiskit is imported lazily.
"""

from __future__ import annotations

from typing import Literal


def run(
    q: int,
    pair: Literal["same", "orthogonal"] = "same",
    shots: int = 4000,
    backend: str = "aer",
    kind: Literal["ancilla", "destructive"] = "ancilla",
) -> dict:
    """SWAP-test a toy pair of q-qubit fingerprint states and summarise the run.

    pair: "same" (identical states, a noiseless test never reads 1) or "orthogonal" (reads 1 half the time).
    backend: "aer" (noiseless), "aer-noisy:<FakeBackend>" (a fake IBM backend's noise model), or "ibm:<device>".
    kind: "ancilla" (2q+1 qubits) or "destructive" (2q qubits, Bell-basis measurement).
    Returns a dict in the format of `swapprint.circuits.run_swap_test`.
    """
    if backend == "aer":
        raise NotImplementedError("backend 'aer' arrives in milestone C1 (Darshan)")
    if backend.startswith("aer-noisy:"):
        raise NotImplementedError("noisy toy runs arrive in milestone C2 (Darshan)")
    if backend.startswith("ibm:"):
        raise NotImplementedError("IBM toy runs arrive in milestone C3 (Darshan)")
    raise ValueError(f"unknown backend {backend!r}; expected 'aer', 'aer-noisy:<FakeBackend>' or 'ibm:<device>'")
