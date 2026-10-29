"""SWAP-test circuits ported from the verified swap_reference.py.

Amplitude index i assigns bit k to qubit k. Registers are a, b, then anc
(qubit 2q); classical register c measures anc, or a then b for destructive.
Qiskit and Aer are imported only inside functions.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np

from ._execution import outcome_bit, run_local

if TYPE_CHECKING:
    from qiskit import QuantumCircuit
    from .fingerprint import Fingerprint


def _sign_state_circuit(c, method="diagonal"):
    """Reference sign preparation, including global phase and ANF/mcz option."""
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import DiagonalGate, ZGate

    c = np.asarray(c)
    m = len(c)
    q = m.bit_length() - 1
    if q < 1 or m != 1 << q or c.ndim != 1 or not np.isin(c, (0, 1)).all():
        raise ValueError("codeword must be a 1-D binary array of power-of-two length >= 2")
    qc = QuantumCircuit(q, name=f"h_c[{q}]")
    qc.h(range(q))
    if method == "diagonal":
        qc.append(DiagonalGate((1.0 - 2.0 * c).tolist()), range(q))
    elif method == "mcz":
        a = np.array(c, dtype=np.uint8)
        k = 1
        while k < len(a):
            blk = a.reshape(-1, 2, k)
            blk[:, 1, :] ^= blk[:, 0, :]
            k <<= 1
        for monomial in np.flatnonzero(a):
            qs = [k for k in range(q) if (int(monomial) >> k) & 1]
            if not qs:
                qc.global_phase += np.pi
            elif len(qs) == 1:
                qc.z(qs[0])
            else:
                qc.append(ZGate().control(len(qs) - 1), qs)
    else:
        raise ValueError("method must be 'diagonal' or 'mcz'")
    return qc


def _check_unit(fp, unit):
    if not isinstance(unit, (int, np.integer)) or not 0 <= unit < fp.data.shape[0]:
        raise ValueError(f"unit must be in [0, {fp.data.shape[0]})")


def _check_pair(a, b, unit):
    if (a.mode, a.version, a.q, a.grid, a.data.shape) != (b.mode, b.version, b.q, b.grid, b.data.shape):
        raise ValueError("cannot compare fingerprints of different versions or shapes")
    _check_unit(a, unit)


def state_circuit(fp: Fingerprint, unit: int) -> QuantumCircuit:
    """Prepare signs on fp.q qubits, or FRQI with colour qubit 6.

    UCRYGate takes its target FIRST: [6, 0, 1, 2, 3, 4, 5]. Thus amplitudes
    0..63 are cos(theta)/8, and 64..127 are sin(theta)/8. Positions 48..63
    have zero angles in FRQI fingerprints.
    """
    _check_unit(fp, unit)
    if fp.mode in ("strict", "perceptual"):
        if fp.data.shape[1] != 1 << fp.q:
            raise ValueError("sign codeword length must equal 2**fp.q")
        return _sign_state_circuit(fp.data[unit])
    if fp.mode != "frqi" or fp.q != 7 or fp.data.shape[1] != 64:
        raise ValueError("expected a sign fingerprint or 7-qubit FRQI fingerprint")
    from qiskit import QuantumCircuit
    from qiskit.circuit.library import UCRYGate

    qc = QuantumCircuit(7, name="frqi")
    qc.h(range(6))
    qc.append(UCRYGate((2 * fp.data[unit]).tolist()), [6, *range(6)])
    return qc


def _swap_prepared(prep_a, prep_b, kind):
    """Reference SWAP-test layout and classical measurement wiring."""
    from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister

    if kind not in ("ancilla", "destructive"):
        raise ValueError("kind must be 'ancilla' or 'destructive'")
    q = prep_a.num_qubits
    a, b = QuantumRegister(q, "a"), QuantumRegister(q, "b")
    regs = [a, b]
    if kind == "ancilla":
        anc = QuantumRegister(1, "anc")
        regs.append(anc)
    c = ClassicalRegister(1 if kind == "ancilla" else 2 * q, "c")
    qc = QuantumCircuit(*regs, c, name=f"swap_{kind}_q{q}")
    qc.compose(prep_a, a, inplace=True)
    qc.compose(prep_b, b, inplace=True)
    if kind == "ancilla":
        qc.h(anc[0])
        for i in range(q):
            qc.cswap(anc[0], a[i], b[i])
        qc.h(anc[0])
        qc.measure(anc[0], c[0])
    else:
        for i in range(q):
            qc.cx(a[i], b[i])
            qc.h(a[i])
        qc.measure(a, c[:q])
        qc.measure(b, c[q:])
    return qc


def swap_test(
    fp_a: Fingerprint, fp_b: Fingerprint, unit: int, kind: Literal["ancilla", "destructive"] = "ancilla"
) -> QuantumCircuit:
    """Build an ancilla (2q+1) or destructive Bell-basis (2q) SWAP test.

    Destructive outcomes are parity(popcount(a & b)), with clbit i = a_i
    and clbit q+i = b_i, exactly as in the reference.
    """
    _check_pair(fp_a, fp_b, unit)
    return _swap_prepared(state_circuit(fp_a, unit), state_circuit(fp_b, unit), kind)


def _hardware_cost(qc, mode, kind, q):
    from ._hardware_costs import COSTS

    if (mode, kind, q) in COSTS:
        return COSTS[mode, kind, q]
    from qiskit import transpile

    isa = transpile(qc, basis_gates=["cx", "rz", "sx", "x"], optimization_level=3, seed_transpiler=2026)
    return sum(i.operation.num_qubits == 2 for i in isa.data), isa.depth()


def _unit_p1(a, b, unit):
    if a.mode == "frqi":
        overlap = np.cos(a.data[unit] - b.data[unit]).mean()
    else:
        overlap = 1 - 2 * np.count_nonzero(a.data[unit] != b.data[unit]) / a.data.shape[1]
    return float(np.clip((1 - overlap**2) / 2, 0, 0.5))


def _run_unit_memory(fp_a, fp_b, unit, shots=1024, kind="ancilla", seed=None):
    """Real Aer per-shot SWAP outcomes, for compare's traced units."""
    qc = swap_test(fp_a, fp_b, unit, kind)
    _, _, _, _, memory = run_local(qc, shots, seed=seed, memory=True)
    return np.array([outcome_bit(key, kind, fp_a.q) for key in memory], dtype=np.int64)


def run_swap_test(
    fp_a: Fingerprint,
    fp_b: Fingerprint,
    unit: int,
    shots: int = 1024,
    backend: str = "aer",
    kind: Literal["ancilla", "destructive"] = "ancilla",
    seed: int | None = None,
) -> dict:
    """Run on ideal Aer; seconds measures Aer transpilation plus execution.

    Hardware costs use [cx, rz, sx, x], all-to-all, optimization_level=3.
    The first q=11 cost transpile took ~3 s, so canonical mode/kind costs
    are cached on disk in _hardware_costs.py, computed once on representative
    image units (see that module for provenance). They approximate other units;
    generic diagonal CX counts vary slightly with the signs. Noncanonical q
    uses this circuit's actual cost. Aer keeps diagonal and cswap native.
    """
    if backend != "aer":
        if backend.startswith(("aer-noisy:", "ibm:")):
            raise NotImplementedError("noisy/hardware backends use small fingerprints via sp.toy.run")
        raise ValueError(f"unknown backend {backend!r}; expected 'aer'")
    qc = swap_test(fp_a, fp_b, unit, kind)
    counts, _, _, seconds, _ = run_local(qc, shots, seed=seed)
    ones = sum(n for key, n in counts.items() if outcome_bit(key, kind, fp_a.q))
    n2, depth = _hardware_cost(qc, fp_a.mode, kind, fp_a.q)
    return dict(ones=ones, shots=shots, p1_est=ones / shots, p1_exact=_unit_p1(fp_a, fp_b, unit),
                qubits=qc.num_qubits, two_qubit_gates=n2, depth=depth, seconds=seconds)


def example_circuit(q: int = 2, kind: Literal["ancilla", "destructive"] = "ancilla") -> QuantumCircuit:
    """Two fixed toy sign states, with H/diagonal/cswap left readable for draw('mpl')."""
    if not isinstance(q, (int, np.integer)) or q < 1:
        raise ValueError("q must be an integer >= 1")
    ca = np.zeros(1 << q, dtype=np.uint8)
    ca[-1] = 1
    cb = ca.copy()
    cb[0] ^= 1
    return _swap_prepared(_sign_state_circuit(ca), _sign_state_circuit(cb), kind)
