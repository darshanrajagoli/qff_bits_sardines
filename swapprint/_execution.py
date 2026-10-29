"""Local execution and readout correction ported from swap_reference.py (Qiskit 2.6.1).

Classical bit j is the j-th bit of the counts integer; strings are MSB first.
All Qiskit imports stay inside functions.
"""
from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from qiskit import QuantumCircuit

KINDS = ("ancilla", "destructive")

def _key_to_int(key) -> tuple[int, int | None]:
    """counts key -> (integer whose bit j is clbit j, number of bits, or None if not knowable)."""
    if isinstance(key, (int, np.integer)):
        return int(key), None
    s = str(key).replace(" ", "")
    if s.startswith(("0x", "0X")):
        return int(s, 16), None
    return int(s, 2), len(s)


def outcome_bit(key, kind: str, q: int) -> int:
    """1 if this measurement outcome counts as a '1' of the SWAP test."""
    k, nbits = _key_to_int(key)
    if kind == "ancilla":
        return k & 1
    if kind == "destructive":
        if nbits is not None and nbits != 2 * q:
            raise ValueError(f"destructive key {key!r} has {nbits} bits, expected 2q = {2 * q}")
        mask = (1 << q) - 1
        a, b = k & mask, (k >> q) & mask        # clbit i = a_i, clbit q+i = b_i
        return (a & b).bit_count() & 1          # parity of sum_i a_i b_i (= number of singlets)
    raise ValueError(f"kind must be one of {KINDS}")


def p1_from_counts(counts: dict, kind: str, q: int, readout_cal=None) -> float:
    """Estimate P(1) from the counts of a swap_test() circuit.

    readout_cal: optional (e01, e10) per-clbit readout error rates, as returned by run(..., readout_cal=True).
                 The counts are then corrected by inverting the tensored (independent per-bit)
                 confusion matrices before the SWAP statistic is computed. The result is clipped to [0, 1].
    """
    total = sum(counts.values())
    if total == 0:
        raise ValueError("empty counts")
    if readout_cal is None:
        return sum(n for key, n in counts.items() if outcome_bit(key, kind, q)) / total
    e01, e10 = (np.asarray(x, dtype=float) for x in readout_cal)
    n = len(e01)
    if n != (1 if kind == "ancilla" else 2 * q):
        raise ValueError(f"readout_cal covers {n} clbits; a {kind} test with q={q} has "
                         f"{1 if kind == 'ancilla' else 2 * q}")
    p = np.zeros(1 << n)
    for key, c in counts.items():
        p[_key_to_int(key)[0]] += c
    t = (p / p.sum()).reshape([2] * n)               # axis n-1-j <-> clbit j
    for j in range(n):
        A = np.array([[1 - e01[j], e10[j]], [e01[j], 1 - e10[j]]])   # A[measured, true]
        ax = n - 1 - j
        t = np.moveaxis(np.tensordot(np.linalg.inv(A), t, axes=([1], [ax])), 0, ax)
    quasi = t.reshape(-1)
    k = np.arange(1 << n)
    if kind == "ancilla":
        ones = (k & 1) == 1
    else:
        mask = (1 << q) - 1
        ones = (np.bitwise_count((k & mask) & ((k >> q) & mask)) & 1) == 1
    return float(np.clip(quasi[ones].sum(), 0.0, 1.0))




def _measured_physical_qubits(isa: QuantumCircuit) -> list[int]:
    """clbit j -> index of the (physical) qubit measured into it."""
    m = {isa.find_bit(i.clbits[0]).index: isa.find_bit(i.qubits[0]).index
         for i in isa.data if i.operation.name == "measure"}
    return [m[j] for j in range(len(m))]


def _calibration_circuits(isa: QuantumCircuit) -> list[QuantumCircuit]:
    """All-0 and all-1 preparations on exactly the physical qubits / clbits that `isa` measures."""
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

    phys = _measured_physical_qubits(isa)
    cals = []
    for flip in (0, 1):
        cal = QuantumCircuit(QuantumRegister(isa.num_qubits, "q"), ClassicalRegister(len(phys), "c"),
                             name=f"readout_cal_{flip}")
        if flip:
            cal.x(phys)
        cal.measure(phys, range(len(phys)))
        cals.append(cal)
    return cals


def _confusion(counts0: dict, counts1: dict, n: int):
    """e01[j] = P(read 1 | prepared 0), e10[j] = P(read 0 | prepared 1) for clbit j."""
    bits = np.arange(n)

    def frac_ones(counts):
        acc = np.zeros(n)
        for key, c in counts.items():
            acc += c * ((_key_to_int(key)[0] >> bits) & 1)
        return acc / sum(counts.values())

    return frac_ones(counts0), 1.0 - frac_ones(counts1)




def run_local(qc, shots=4000, backend=None, seed=None, readout_cal=False, memory=False):
    """Reference run() local dispatch; also expose ISA circuit, memory and elapsed time.

    Ideal Aer uses Qiskit's built-in, seeded native-basis translation stage.
    Device simulators follow the reference's full level-3 preset dispatch.
    Calibration circuits measure exactly the physical wires selected by the transpiler,
    in the same job as the test. Real IBM dispatch is deliberately excluded in C1.
    """
    from qiskit.transpiler import generate_preset_pass_manager
    from qiskit_aer import AerSimulator

    if shots < 1:
        raise ValueError("shots must be >= 1")
    ideal = backend is None
    if ideal:
        backend = AerSimulator(method="statevector")
    start = perf_counter()
    if ideal:
        # Aer has all-to-all connectivity and executes diagonal/cswap natively.
        # Use Qiskit's built-in translation stage directly: enumerating every
        # installed preset plugin imports IBM Runtime and costs ~2.7 s cold.
        # This is the same basis-translation stage used by the preset manager;
        # no layout/routing/optimization is needed for these native circuits.
        from qiskit.transpiler import PassManagerConfig
        from qiskit.transpiler.preset_passmanagers.builtin_plugins import BasisTranslatorPassManager

        config = PassManagerConfig(basis_gates=backend.configuration().basis_gates,
                                   target=backend.target, seed_transpiler=seed)
        pm = BasisTranslatorPassManager().pass_manager(config, optimization_level=3)
    else:
        pm = generate_preset_pass_manager(optimization_level=3, backend=backend, seed_transpiler=seed)
    isa = pm.run(qc)
    circuits = [isa] + (_calibration_circuits(isa) if readout_cal else [])
    result = backend.run(circuits, shots=shots, seed_simulator=seed, memory=memory).result()
    seconds = perf_counter() - start
    counts = result.get_counts(0)
    cal = (_confusion(result.get_counts(1), result.get_counts(2), isa.num_clbits)
           if readout_cal else None)
    return counts, cal, isa, seconds, result.get_memory(0) if memory else None
