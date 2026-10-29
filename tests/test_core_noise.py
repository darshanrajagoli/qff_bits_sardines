"""Fast C2 checks: joint bootstrap, seed compatibility, exact threshold design."""
import numpy as np
import pytest
from scipy.stats import binom

from experiments.core_noise import cost_cache_key, exact_threshold
from swapprint._execution import bootstrap_p1, p1_from_counts, run_local
from swapprint.toy import run


@pytest.mark.parametrize("kind,q", [("ancilla", 1), ("destructive", 2)])
def test_bootstrap_matches_scalar_joint_multinomial(kind, q):
    n = 1 if kind == "ancilla" else 2*q
    size = 1 << n
    measured = np.arange(1, size+1) * 7
    cal0 = np.ones(size, dtype=int)
    cal1 = np.ones(size, dtype=int)
    cal0[0] = cal1[-1] = 2000
    counts = dict(enumerate(measured))
    cals = [dict(enumerate(cal0)), dict(enumerate(cal1))]
    rng = np.random.default_rng(19)
    sampled = [rng.multinomial(int(p.sum()), p/p.sum(), size=200) for p in (measured, cal0, cal1)]
    bits = (np.arange(size)[:, None] >> np.arange(n)) & 1
    raw, corrected = [], []
    for test, zero, one in zip(*sampled):
        e01 = zero @ bits / zero.sum()
        e10 = 1 - one @ bits / one.sum()
        raw.append(p1_from_counts(dict(enumerate(test)), kind, q))
        corrected.append(p1_from_counts(dict(enumerate(test)), kind, q, (e01, e10)))
    actual = bootstrap_p1(counts, kind, q, cals, resamples=200, seed=19)
    for prefix, samples in (("raw", raw), ("cal", corrected)):
        assert actual[f"p1_{prefix}_lo"] == pytest.approx(np.quantile(samples, .025))
        assert actual[f"p1_{prefix}_hi"] == pytest.approx(np.quantile(samples, .975))


def test_calibration_uncertainty_is_resampled():
    # The test histogram is nearly deterministic; calibration shots dominate.
    counts = {0: 500_000, 1: 500_000}
    fixed = bootstrap_p1(counts, "ancilla", 1, resamples=1000, seed=3)
    joint = bootstrap_p1(counts, "ancilla", 1, [{0: 90, 1: 10}, {0: 20, 1: 80}],
                         resamples=1000, seed=3)
    assert joint["p1_cal_hi"] - joint["p1_cal_lo"] > 10*(fixed["p1_raw_hi"] - fixed["p1_raw_lo"])
    with pytest.raises(ValueError, match="resamples"):
        bootstrap_p1(counts, "ancilla", 1, resamples=0)


def test_execution_independent_seeds_and_details(monkeypatch):
    from qiskit import QuantumCircuit
    import qiskit.transpiler
    seen = {}
    qc = QuantumCircuit(1, 1)
    qc.measure(0, 0)

    class PM:
        def run(self, circuit):
            return circuit

    def pm(**kwargs):
        seen["transpile"] = kwargs["seed_transpiler"]
        return PM()

    class Backend:
        def run(self, circuits, **kwargs):
            seen["simulator"] = kwargs["seed_simulator"]
            return self

        def result(self):
            return self

        def get_counts(self, index):
            return {"0": 8, "1": 2} if index != 2 else {"0": 1, "1": 9}

    monkeypatch.setattr(qiskit.transpiler, "generate_preset_pass_manager", pm)
    result = run_local(qc, 10, Backend(), seed=5, readout_cal=True,
                       transpile_seed=11, simulator_seed=17, return_details=True)
    assert seen == {"transpile": 11, "simulator": 17}
    assert len(result) == 6
    assert result[5]["physical_qubits"] == [0]
    assert len(result[5]["calibration_counts"]) == 2
    assert len(run_local(qc, 10, Backend(), seed=5)) == 5
    assert seen == {"transpile": 5, "simulator": 5}


def test_toy_bootstrap_is_opt_in_and_reproducible():
    options = dict(q=2, pair="near", shots=128, kind="destructive", seed=4,
                   transpile_seed=9, simulator_seed=21, readout_cal=True)
    result = run(**options, bootstrap_resamples=100)
    repeated = run(**options, bootstrap_resamples=100)
    assert result["sampling_details"] == repeated["sampling_details"]
    for key in ("p1_raw_lo", "p1_raw_hi", "p1_cal_lo", "p1_cal_hi"):
        assert result[key] == repeated[key]
    plain = run(**options)
    assert plain["ones"] == result["ones"]
    assert "sampling_details" not in plain and "p1_raw_lo" not in plain
    with pytest.raises(ValueError, match="bootstrap_resamples"):
        run(1, bootstrap_resamples=-1)


@pytest.mark.parametrize("p0,p1", [(.02, .25), (.1, .3), (0, .5)])
def test_exact_threshold_is_minimal_and_obeys_strict_rule(p0, p1):
    row = exact_threshold(p0, p1)
    assert row["status"] == "ok"
    k, cutoff = row["k"], row["cutoff"]
    assert row["tau"] == cutoff/k
    assert binom.sf(cutoff, k, p0) <= .01
    assert binom.sf(cutoff, k, p1) >= .99
    # Every smaller shot count fails for every possible integer cutoff.
    for earlier in range(1, k):
        c = np.arange(earlier+1)
        assert not ((binom.sf(c, earlier, p0) <= .01) &
                    (binom.sf(c, earlier, p1) >= .99)).any()


def test_threshold_no_separation():
    assert exact_threshold(.3, .2)["status"] == "no separation"
    assert exact_threshold(.3, .3)["k"] is None


def test_cost_cache_uses_canonical_snapshot():
    from types import SimpleNamespace

    def backend(values):
        return SimpleNamespace(properties=lambda: SimpleNamespace(to_dict=lambda: values))

    a = cost_cache_key(backend({"name": "fake", "error": .01}))
    b = cost_cache_key(backend({"error": .01, "name": "fake"}))
    changed = cost_cache_key(backend({"error": .02, "name": "fake"}))
    assert a == b and a != changed
