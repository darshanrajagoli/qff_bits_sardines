"""C3: real client-side Runtime API in offline local testing mode; no account."""
import json

import pytest

from swapprint import toy
from swapprint._execution import (decode_runtime_batch, estimate_runtime_seconds,
                                  prepare_runtime_batch, runtime_backend)


def test_runtime_local_batch_calibration_and_recovery(monkeypatch):
    from qiskit_ibm_runtime import Executor
    from qiskit_ibm_runtime.fake_provider import FakeFez

    backend = FakeFez()
    original = Executor.run
    calls, saved = [], {}

    def run(self, program, **kwargs):
        calls.append([item.circuit for item in program.items])
        assert self._SCHEMA_VERSION == "v1.1"
        return original(self, program, **kwargs)

    def persist(job, manifest):
        # This must happen before the blocking result() call.
        saved.update(json.loads(json.dumps(manifest)))
        saved["job"] = job

    monkeypatch.setattr(Executor, "run", run)
    # Repeat the same circuit to exercise shared calibration; include destructive
    # Bell parity, whose classical bit order differs from the ancilla statistic.
    specs = [dict(q=1, pair="orthogonal", shots=256, seed=2026,
                  transpile_seed=7, simulator_seed=17, bootstrap_resamples=100),
             dict(q=1, pair="orthogonal", shots=256, seed=2026,
                  transpile_seed=7, simulator_seed=17, bootstrap_resamples=100),
             dict(q=2, kind="destructive", pair="near", shots=256, seed=2026,
                  transpile_seed=7, simulator_seed=17, bootstrap_resamples=100)]
    rows = toy.run_batch(specs, backend, on_submitted=persist)
    assert len(calls) == 1
    assert len(calls[0]) == 7  # 3 tests + 2 distinct pairs of calibrations
    assert saved["circuits"][0]["calibration_indices"] == saved["circuits"][1]["calibration_indices"]
    assert 0 < estimate_runtime_seconds(calls[0], backend, 4000) < 180
    for row in rows:
        assert sum(row["raw_counts"].values()) == row["shots"] == 256
        assert row["device"] == "fake_fez" and row["job_id"] == saved["job_id"]
        assert .2 < row["p1_raw"] < .7
        assert 0 <= row["p1_cal_lo"] <= row["p1_cal_hi"] <= 1
        assert row["depth"] > 0 and row["two_qubit_gates"] > 0
        assert len(row["sampling_details"]["calibration_counts"]) == 2
    recovered = decode_runtime_batch(saved["job"].result(), saved["circuits"],
                                     job_id=saved["job_id"], device=saved["device"], date=saved["date"])
    assert [r["raw_counts"] for r in recovered] == [r["raw_counts"] for r in rows]
    assert [r["p1_cal_lo"] for r in recovered] == [r["p1_cal_lo"] for r in rows]
    # Calibrations retain exact physical wires and clbit order through ISA translation.
    from swapprint._execution import _measured_physical_qubits
    for m in saved["circuits"]:
        for index in m["calibration_indices"]:
            assert _measured_physical_qubits(calls[0][index]) == m["physical_qubits"]


def test_ibm_selectors_use_saved_service():
    class Service:
        def backend(self, name):
            return name

        def least_busy(self, **kwargs):
            assert kwargs == dict(operational=True, simulator=False)
            return "least"

    assert runtime_backend("ibm:ibm_fez", Service()) == "ibm_fez"
    assert runtime_backend("ibm:least_busy", Service()) == "least"
    with pytest.raises(ValueError):
        runtime_backend("ibm:", Service())


@pytest.mark.parametrize("specs", [[], [dict(q=0)], [dict(q=1, shots=0)],
    [dict(q=1, shots=1.5)], [dict(q=1, bootstrap_resamples=-1)],
    [dict(q=1, shots=100), dict(q=2, shots=200)], [dict(q=1, extra=3)]])
def test_invalid_batches_fail_before_account_loading(monkeypatch, specs):
    import qiskit_ibm_runtime

    def no_account(*args, **kwargs):
        pytest.fail("invalid inputs must not load an account")

    monkeypatch.setattr(qiskit_ibm_runtime, "QiskitRuntimeService", no_account)
    with pytest.raises(ValueError):
        toy.run_batch(specs, "ibm:least_busy")


def test_single_ibm_run_delegates_all_options(monkeypatch):
    def batch(specs, backend):
        assert backend == "ibm:ibm_fez"
        assert specs[0]["q"] == 3 and specs[0]["readout_cal"]
        assert specs[0]["kind"] == "destructive"
        assert specs[0]["transpile_seed"] == 91
        return [{"job_id": "test"}]

    monkeypatch.setattr(toy, "run_batch", batch)
    assert toy.run(3, backend="ibm:ibm_fez", kind="destructive",
                   readout_cal=True, transpile_seed=91) == {"job_id": "test"}


def test_remote_transport_uses_service_compatible_qpy_without_network(monkeypatch):
    """Exercise serialization, which local testing mode otherwise bypasses."""
    from qiskit_ibm_runtime import Executor
    from qiskit_ibm_runtime.fake_provider import FakeFez
    from swapprint._execution import submit_runtime_batch

    backend = FakeFez()
    backend._instance = "offline-test-instance"
    circuits, specs = toy._runtime_specs([dict(q=2, kind="destructive", seed=2026,
                                               transpile_seed=7, shots=128)], backend)
    pubs, manifests = prepare_runtime_batch(circuits, specs, backend)
    original_init = Executor.__init__
    captured = {}

    class RemoteService:
        is_local = False

        def _run(self, **kwargs):
            captured.update(kwargs)
            return "no network"

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self._service = RemoteService()

    monkeypatch.setattr(Executor, "__init__", init)
    assert submit_runtime_batch(pubs, backend, 128) == "no network"
    assert captured["program_id"] == "executor"
    inputs = captured["inputs"]
    assert inputs["schema_version"] == "v1.1"
    assert inputs["quantum_program"]["circuits"]["qpy_version"] == 17
    from qiskit_ibm_runtime.quantum_program.params_converters import QUANTUM_PROGRAM_PARAMS_CONVERTERS
    converter = QUANTUM_PROGRAM_PARAMS_CONVERTERS["v1.1"]
    program, _ = converter.decoder(converter.model.model_validate(inputs))
    assert len(program.items) == len(pubs)
    for before, item in zip(pubs, program.items, strict=True):
        assert item.circuit == before
    # Selecting the transport on one instance leaves the SDK default unchanged.
    assert Executor._SCHEMA_VERSION == "v2.0"
