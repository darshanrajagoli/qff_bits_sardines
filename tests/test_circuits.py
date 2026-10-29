"""C1: state amplitudes, circuit statistics, Aer memory and reference readout calibration."""
from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector
from qiskit_aer import AerSimulator

import swapprint as sp
from swapprint._execution import _calibration_circuits, _measured_physical_qubits, outcome_bit, p1_from_counts, run_local
from swapprint.circuits import _run_unit_memory, _sign_state_circuit
from swapprint.toy import _toy_codewords
from swapprint.validate import _pairs, wilson

KEYS = {"ones", "shots", "p1_est", "p1_exact", "qubits", "two_qubit_gates", "depth", "seconds"}
KINDS = ("ancilla", "destructive")


def unit_fp(data, mode="strict", q=None):
    data = np.asarray(data)
    if q is None:
        q = 7 if mode == "frqi" else len(data).bit_length() - 1
    return sp.Fingerprint(mode, q, (1, 1), 4, data[None, :], f"test/{mode}/q{q}")


@pytest.mark.parametrize("mode", ["strict", "perceptual"])
@pytest.mark.parametrize("q", range(1, 7))
def test_sign_amplitudes(mode, q):
    rng = np.random.default_rng(70 + q)
    for bits in (rng.integers(0, 2, 1 << q), np.eye(1 << q, dtype=int)[-1]):
        fp = unit_fp(bits, mode)
        sv = Statevector(sp.circuits.state_circuit(fp, 0)).data
        np.testing.assert_allclose(sv, (1 - 2 * bits) / math.sqrt(len(bits)), atol=1e-12)
        other = unit_fp(rng.integers(0, 2, 1 << q), mode)
        ov = np.vdot(sv, Statevector(sp.circuits.state_circuit(other, 0)).data)
        assert ov == pytest.approx(sp.overlaps(fp, other)[0, 0], abs=1e-12)


def test_frqi_amplitudes_and_overlap():
    img = sp.synthetic.artwork(7)
    a = sp.fingerprint(img, "frqi")
    b = sp.fingerprint(sp.edits.patch(img, y=0, x=0, size=4), "frqi")
    for fp in (a, b):
        sv = Statevector(sp.circuits.state_circuit(fp, 0)).data
        expected = np.r_[np.cos(fp.data[0]), np.sin(fp.data[0])] / 8
        np.testing.assert_allclose(sv, expected, atol=1e-12)
        # Colour is the highest bit; the zero-padded positions have no |1> amplitude.
        np.testing.assert_allclose(sv[112:128], 0, atol=1e-12)
        np.testing.assert_allclose(sv[48:64], 1 / 8, atol=1e-12)
    overlap = np.vdot(Statevector(sp.circuits.state_circuit(a, 0)).data,
                      Statevector(sp.circuits.state_circuit(b, 0)).data)
    assert overlap == pytest.approx(sp.overlaps(a, b)[0, 0], abs=1e-12)


def circuit_p1(a, b, kind):
    qc = sp.circuits.swap_test(a, b, 0, kind).remove_final_measurements(inplace=False)
    sv = Statevector(qc)
    if kind == "ancilla":
        return sv.probabilities([2 * a.q])[1]
    probs = sv.probabilities()
    indices = np.arange(len(probs), dtype=np.uint64)
    mask = (1 << a.q) - 1
    parity = np.bitwise_count((indices & mask) & ((indices >> a.q) & mask)) & 1
    return probs[parity == 1].sum()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("q", range(1, 5))
def test_swap_statevector_signs(kind, q):
    rng = np.random.default_rng(q)
    ca = rng.integers(0, 2, 1 << q)
    for flips in sorted({0, 1, (1 << q) // 2, (1 << q) - 1, 1 << q}):
        cb = ca.copy()
        cb[rng.permutation(len(ca))[:flips]] ^= 1
        a, b = unit_fp(ca), unit_fp(cb)
        exact = (1 - sp.overlaps(a, b)[0, 0] ** 2) / 2
        assert circuit_p1(a, b, kind) == pytest.approx(exact, abs=1e-12)


@pytest.mark.parametrize("kind", KINDS)
def test_swap_statevector_frqi(kind):
    rng = np.random.default_rng(17)
    a, b = [unit_fp(np.r_[rng.uniform(0, np.pi / 2, 48), np.zeros(16)], "frqi") for _ in range(2)]
    exact = (1 - sp.overlaps(a, b)[0, 0] ** 2) / 2
    assert circuit_p1(a, b, kind) == pytest.approx(exact, abs=1e-12)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("mode", ["strict", "perceptual", "frqi"])
def test_identical_aer_never_one(kind, mode):
    rng = np.random.default_rng(15)
    data = (np.r_[rng.random(48), np.zeros(16)] if mode == "frqi" else rng.integers(0, 2, 16))
    a = unit_fp(data, mode)
    res = sp.circuits.run_swap_test(a, a, 0, shots=2048, kind=kind, seed=5)
    assert res["ones"] == res["p1_est"] == res["p1_exact"] == 0


@pytest.mark.parametrize("kind", KINDS)
def test_sampled_statistics_and_keys(kind):
    ca, cb = _toy_codewords(4, "near", "random", 42)
    a, b = unit_fp(ca), unit_fp(cb)
    res = sp.circuits.run_swap_test(a, b, 0, shots=4096, kind=kind, seed=42)
    assert set(res) == KEYS
    exact = (1 - sp.overlaps(a, b)[0, 0] ** 2) / 2
    sigma = math.sqrt(exact * (1 - exact) / res["shots"])
    assert abs(res["p1_est"] - exact) < 4 * sigma
    assert res["qubits"] == 2 * a.q + (kind == "ancilla")
    assert res["two_qubit_gates"] > 0 and res["depth"] > 0 and res["seconds"] > 0
    assert res == {**res, "p1_est": res["ones"] / res["shots"]}
    repeated = sp.circuits.run_swap_test(a, b, 0, shots=4096, kind=kind, seed=42)
    assert repeated["ones"] == res["ones"]


@pytest.mark.parametrize("key", ["100001", "100 001", "0x21", 33])
def test_reference_nonsymmetric_bit_keys(key):
    assert outcome_bit(key, "destructive", 3) == 0
    assert outcome_bit("001001", "destructive", 3) == 1


@pytest.mark.parametrize("a_val,b_val", [(1, 4), (1, 1), (6, 3), (7, 5)])
def test_real_measurement_wiring(a_val, b_val):
    a = unit_fp(np.zeros(8, np.uint8))
    template = sp.circuits.swap_test(a, a, 0, "destructive")
    qc = QuantumCircuit(*template.qregs, *template.cregs)
    for offset, value in ((0, a_val), (3, b_val)):
        for bit in range(3):
            if (value >> bit) & 1:
                qc.x(offset + bit)
    for inst in template.data:
        if inst.operation.name == "measure":
            qc.append(inst)
    counts, _, _, _, _ = run_local(qc, shots=16, seed=5)
    assert p1_from_counts(counts, "destructive", 3) == (a_val & b_val).bit_count() % 2
    assert [(r.name, len(r)) for r in template.cregs] == [("c", 6)]


@pytest.mark.parametrize("kind", KINDS)
def test_example_draw(kind):
    qc = sp.circuits.example_circuit(kind=kind)
    assert str(qc.draw("text"))
    assert qc.count_ops()["diagonal"] == 2
    if kind == "ancilla":
        assert qc.count_ops()["cswap"] == 2
        assert [r.name for r in qc.qregs] == ["a", "b", "anc"]


@pytest.fixture(scope="module")
def image_pairs():
    img = sp.synthetic.artwork(1)
    a = sp.fingerprint(img)
    return a, sp.fingerprint(sp.edits.pixel(img))


@pytest.mark.parametrize("kind", KINDS)
def test_compare_actual_memory(image_pairs, monkeypatch, kind):
    a, b = image_pairs
    seen = []
    original = AerSimulator.run

    def spy(self, *args, **kwargs):
        seen.append(kwargs.get("memory"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(AerSimulator, "run", spy)
    cmp = sp.compare(a, b, backend="aer", kind=kind, seed=17)
    assert cmp.tampered
    assert cmp.circuit_tiles == [2080] and seen == [True]
    expected = _run_unit_memory(a, b, 2080, cmp.shots, kind, 17 + 2080).tolist()
    assert cmp.traces[2080] == expected
    assert cmp.ones.ravel()[2080] == sum(expected)
    assert cmp.first_detection[2080] == expected.index(1) + 1
    again = sp.compare(a, b, backend="aer", kind=kind, seed=17)
    assert again.to_dict() == cmp.to_dict()


@pytest.mark.parametrize("kind", KINDS)
def test_compare_identical(image_pairs, kind):
    a, _ = image_pairs
    cmp = sp.compare(a, a, backend="aer", kind=kind, seed=1)
    assert not cmp.tampered and not cmp.ones.any()
    assert cmp.circuit_tiles == [0, 1, 2, 3]
    assert all(trace == [0] * cmp.shots for trace in cmp.traces.values())
    assert all(value is None for value in cmp.first_detection.values())


def test_untraced_binomial_path_and_kind_only_for_aer(image_pairs):
    a, b = image_pairs
    exact = sp.compare(a, b, seed=7, trace_tiles=0, kind="ignored")
    aer = sp.compare(a, b, backend="aer", seed=7, trace_tiles=0)
    np.testing.assert_array_equal(aer.ones, exact.ones)
    assert aer.circuit_tiles == [] and aer.traces == {}


@pytest.mark.parametrize("pair", ["same", "orthogonal", "near"])
@pytest.mark.parametrize("family", ["random", "hadamard"])
@pytest.mark.parametrize("method", ["diagonal", "mcz"])
@pytest.mark.parametrize("kind", KINDS)
def test_toys(pair, family, method, kind):
    res = sp.toy.run(3, pair, shots=4000, kind=kind, family=family, method=method, seed=5)
    overlap = {"same": 1, "orthogonal": 0, "near": 1 - 2 / 8}[pair]
    ideal = (1 - overlap**2) / 2
    assert set(res) == KEYS | {"p1_ideal", "backend", "pair", "family", "q"}
    assert res["p1_ideal"] == res["p1_exact"] == ideal
    assert (res["backend"], res["pair"], res["family"], res["q"]) == ("aer", pair, family, 3)
    if ideal == 0:
        assert res["ones"] == 0
    else:
        assert abs(res["p1_est"] - ideal) < 4 * math.sqrt(ideal * (1 - ideal) / 4000)


@pytest.mark.parametrize("kind", KINDS)
def test_readout_calibration_inverts_known_confusion(kind):
    ca, cb = _toy_codewords(2, "orthogonal", "random", 5)
    cb[0] ^= 1  # overlap 0.5, ideal P(1)=0.375
    a, b = unit_fp(ca), unit_fp(cb)
    sv = Statevector(sp.circuits.swap_test(a, b, 0, kind).remove_final_measurements(inplace=False))
    p = sv.probabilities([4]) if kind == "ancilla" else sv.probabilities()
    n = 1 if kind == "ancilla" else 4
    e01, e10 = np.array([.02, .05, .01, .08])[:n], np.array([.03, .06, .02, .04])[:n]
    t = p.reshape([2] * n)
    for j in range(n):
        confusion = np.array([[1 - e01[j], e10[j]], [e01[j], 1 - e10[j]]])
        axis = n - 1 - j
        t = np.moveaxis(np.tensordot(confusion, t, axes=([1], [axis])), 0, axis)
    counts = dict(enumerate(t.reshape(-1) * 1e6))
    assert abs(p1_from_counts(counts, kind, 2) - .375) > 1e-4
    assert p1_from_counts(counts, kind, 2, (e01, e10)) == pytest.approx(.375, abs=1e-12)
    res = sp.toy.run(2, pair="same", kind=kind, readout_cal=True, seed=5)
    assert res["p1_est_cal"] == res["p1_est"] == 0


@pytest.mark.slow
def test_noisy_fez():
    res = sp.toy.run(2, backend="aer-noisy:FakeFez", kind="destructive", method="mcz",
                     readout_cal=True, seed=7)
    assert 0 <= res["p1_est_cal"] <= 1
    assert 0 < res["p1_est"] < .5 and res["p1_ideal"] == 0
    assert res["two_qubit_gates"] > 0 and res["depth"] > 0


@pytest.mark.slow
@pytest.mark.parametrize("kind", KINDS)
def test_strict_q11_smoke(image_pairs, kind):
    a, b = image_pairs
    res = sp.circuits.run_swap_test(a, b, 2080, shots=2048, kind=kind, seed=11)
    sigma = math.sqrt(res["p1_exact"] * (1 - res["p1_exact"]) / 2048)
    assert abs(res["p1_est"] - res["p1_exact"]) < 4 * sigma
    assert res["qubits"] == 22 + (kind == "ancilla")
    assert res["two_qubit_gates"] > 4000 and res["depth"] > 1000


def test_invalid_circuit_arguments():
    fp = unit_fp([0, 0, 0, 1])
    for unit in (-1, 1, .5):
        with pytest.raises(ValueError, match="unit"):
            sp.circuits.state_circuit(fp, unit)
    with pytest.raises(ValueError, match="versions"):
        sp.circuits.swap_test(fp, replace(fp, version="old"), 0)
    with pytest.raises(ValueError, match="kind"):
        sp.circuits.swap_test(fp, fp, 0, "invalid")
    with pytest.raises(ValueError, match="shots"):
        sp.circuits.run_swap_test(fp, fp, 0, shots=0)
    for backend in ("aer-noisy:FakeFez", "ibm:example"):
        with pytest.raises(NotImplementedError, match="sp.toy.run"):
            sp.circuits.run_swap_test(fp, fp, 0, backend=backend)
    with pytest.raises(ValueError, match="fake backend"):
        sp.toy.run(2, backend="aer-noisy:FakeMissing")


def test_wilson_boundaries():
    lo, hi = wilson(0, 2048)
    assert lo == 0 and 0 < hi < .002
    lo, hi = wilson(2048, 2048)
    assert .998 < lo < 1 and hi == 1


def test_calibration_uses_measured_physical_wires():
    qc = QuantumCircuit(7, 2)
    qc.measure(5, 0)
    qc.measure(2, 1)
    assert _measured_physical_qubits(qc) == [5, 2]
    cals = _calibration_circuits(qc)
    for cal in cals:
        assert _measured_physical_qubits(cal) == [5, 2]
    assert cals[0].count_ops().get("x", 0) == 0
    assert [cals[1].find_bit(i.qubits[0]).index for i in cals[1].data if i.operation.name == "x"] == [5, 2]


def test_validation_pair_design():
    counts = {}
    perceptual_p1 = []
    for pair_type, a, b, unit in _pairs():
        key = (a.mode, pair_type)
        counts[key] = counts.get(key, 0) + 1
        if a.mode == "perceptual":
            p1 = (1 - sp.overlaps(a, b).ravel()[unit] ** 2) / 2
            assert 0.015 <= p1 <= .42
            perceptual_p1.append(p1)
    assert [counts["strict", p] for p in ("identical", "pixel", "unrelated")] == [10, 10, 10]
    assert sum(n for (mode, _), n in counts.items() if mode == "frqi") == 10
    assert len(perceptual_p1) == 10 and min(perceptual_p1) < .07 and max(perceptual_p1) >= .39
