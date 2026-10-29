"""Qiskit circuits for fingerprint states and the SWAP test (milestone C1, Darshan). Stubs in v0.1.

Qiskit is imported lazily inside the functions, so `import swapprint` stays fast and works without it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from qiskit import QuantumCircuit

    from .fingerprint import Fingerprint


def state_circuit(fp: Fingerprint, unit: int) -> QuantumCircuit:
    """Prepare unit `unit`'s state on fp.q qubits.

    strict and perceptual: Hadamards on every qubit, then the signs (-1)^bit_i as a diagonal phase oracle, giving
    (1/sqrt(2^q)) sum_i (-1)^bit_i |i>. frqi: Hadamards on the 6 position qubits, then
    uniformly controlled RY(2 theta_i) on the colour qubit. The FRQI state is
    (1/8) sum_i (cos theta_i |0> + sin theta_i |1>) |i>, with positions 48..63 padded by theta_i = 0.
    """
    raise NotImplementedError("milestone C1 (Darshan)")


def example_circuit(q: int = 2, kind: Literal["ancilla", "destructive"] = "ancilla") -> QuantumCircuit:
    """A small q-qubit-pair SWAP test for the app to draw (milestone C1).

    kind="ancilla" uses 2q+1 qubits; kind="destructive" uses 2q qubits and Bell-basis measurement.
    """
    raise NotImplementedError("milestone C1 (Darshan)")


def swap_test(
    fp_a: Fingerprint, fp_b: Fingerprint, unit: int, kind: Literal["ancilla", "destructive"] = "ancilla"
) -> QuantumCircuit:
    """SWAP test between unit `unit` of two fingerprints.

    kind="ancilla": 2q+1 qubits. Hadamard on the ancilla, q controlled-SWAPs, Hadamard, measure the ancilla, which
    reads 1 with probability (1 - overlap^2) / 2.
    kind="destructive": 2q qubits, no ancilla. A CNOT and a Hadamard on each pair of qubits measure in the Bell basis;
    the parity of the AND of the paired outcomes plays the ancilla's role (Garcia-Escartin and Chamorro-Posada 2013).
    """
    raise NotImplementedError("milestone C1 (Darshan)")


def run_swap_test(
    fp_a: Fingerprint,
    fp_b: Fingerprint,
    unit: int,
    shots: int = 1024,
    backend: str = "aer",
    kind: Literal["ancilla", "destructive"] = "ancilla",
) -> dict:
    """Run `swap_test` for unit `unit` and summarise it.

    Returns {"ones", "shots", "p1_est", "p1_exact", "qubits", "two_qubit_gates", "depth", "seconds"}.
    """
    raise NotImplementedError("milestone C1 (Darshan)")
