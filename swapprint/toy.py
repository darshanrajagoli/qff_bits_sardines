"""Small sign-state experiments, ported from swap_reference.py; imports are lazy."""
from __future__ import annotations

from typing import Literal
from functools import lru_cache

import numpy as np

from ._execution import bootstrap_p1, outcome_bit, p1_from_counts, run_local
from .circuits import _sign_state_circuit, _swap_prepared


def _toy_codewords(q: int, pair: str = "orthogonal", family: str = "hadamard", seed: int = 0):
    """Small test pairs (ca, cb) of length m = 2^q.

    pair   : "same"  (overlap 1, P1 = 0)
             "orthogonal" (overlap exactly 0, P1 = 1/2)
             "near"     (one flipped bit, overlap 1 - 2/m)
    family : "hadamard" -> rows of the Sylvester-Hadamard code, c_i = popcount(r & i) mod 2. These give
                           product states |h_c> = H^q |r>, so preparing them needs no 2q gates.
             "random"   -> seeded random ca with odd weight. The top ANF monomial is then present, so the
                           state is entangled across all q qubits, like a real image tile. The orthogonal
                           partner is cb = ca XOR (random mask with exactly m/2 ones).
    """
    m = 1 << q
    if family == "hadamard":
        row = lambda r: np.array([bin(r & i).count("1") & 1 for i in range(m)], dtype=np.uint8)
        ca = row(m - 1)
        partner = {"same": ca.copy(), "orthogonal": row(0)}
        if pair in partner:
            return ca, partner[pair]
        if pair == "near":
            cb = ca.copy(); cb[m - 1] ^= 1
            return ca, cb
    elif family == "random":
        rng = np.random.default_rng(seed)
        while True:
            ca = rng.integers(0, 2, m).astype(np.uint8)
            if ca.sum() % 2 == 1:
                break
        if pair == "same":
            return ca, ca.copy()
        if pair == "orthogonal":
            mask = np.zeros(m, dtype=np.uint8)
            mask[rng.permutation(m)[: m // 2]] = 1
            return ca, ca ^ mask
        if pair == "near":
            cb = ca.copy(); cb[rng.integers(m)] ^= 1
            return ca, cb
    else:
        raise ValueError(f"unknown family {family!r}")
    raise ValueError(f"unknown pair {pair!r}")



@lru_cache(maxsize=2)
def _noisy_simulator(name):
    import qiskit_ibm_runtime.fake_provider as provider
    from qiskit_aer import AerSimulator

    factory = getattr(provider, name, None) if name.startswith("Fake") else None
    if factory is None or not callable(factory):
        raise ValueError(f"unknown fake backend {name!r}")
    # Density matrices avoid thousands of noisy statevector trajectories for toys.
    return AerSimulator.from_backend(factory(), method="density_matrix", max_parallel_threads=4)


def run(
    q: int,
    pair: Literal["same", "orthogonal", "near"] = "same",
    shots: int = 4000,
    backend = "aer",
    kind: Literal["ancilla", "destructive"] = "ancilla",
    family: str = "random",
    method: str = "diagonal",
    readout_cal: bool = False,
    seed: int | None = None,
    *,
    transpile_seed: int | None = None,
    simulator_seed: int | None = None,
    bootstrap_resamples: int = 0,
) -> dict:
    """Run toy pairs on Aer, fake IBM noise, or IBM hardware / Runtime local mode.

    Costs describe the actual circuit transpiled for the selected backend:
    native-basis translation for ideal Aer, optimization_level=3 with routing
    for fake backends. Readout correction inverts
    independent per-clbit confusion matrices measured on the same physical wires.
    Hadamard same/orthogonal pairs are product states; a near pair's single sign
    flip generally makes its partner entangled. method also accepts "mcz".
    seed fixes the states and remains the default execution/transpiler seed.
    Explicit transpile_seed/simulator_seed vary routing/sampling independently.
    bootstrap_resamples > 0 adds 95% intervals and auditable measurement counts.
    """
    if not isinstance(backend, str) or backend.startswith("ibm:"):
        return run_batch([dict(q=q, pair=pair, shots=shots, kind=kind, family=family,
                               method=method, readout_cal=readout_cal, seed=seed,
                               transpile_seed=transpile_seed, simulator_seed=simulator_seed,
                               bootstrap_resamples=bootstrap_resamples)], backend)[0]
    if backend != "aer" and not backend.startswith("aer-noisy:"):
        raise ValueError(f"unknown backend {backend!r}; expected 'aer', 'aer-noisy:<FakeBackend>' or 'ibm:<device>'")
    if not isinstance(q, (int, np.integer)) or q < 1:
        raise ValueError("q must be an integer >= 1")
    if not isinstance(bootstrap_resamples, (int, np.integer)) or bootstrap_resamples < 0:
        raise ValueError("bootstrap_resamples must be a nonnegative integer")
    ca, cb = _toy_codewords(int(q), pair, family, seed)
    qc = _swap_prepared(_sign_state_circuit(ca, method), _sign_state_circuit(cb, method), kind)
    sim = None
    if backend.startswith("aer-noisy:"):
        name = backend.split(":", 1)[1]
        sim = _noisy_simulator(name)
    output = run_local(qc, shots, sim, seed, readout_cal,
                       transpile_seed=transpile_seed, simulator_seed=simulator_seed,
                       return_details=bool(bootstrap_resamples))
    counts, cal, isa, seconds, _ = output[:5]
    p1 = p1_from_counts(counts, kind, q)
    ideal = float((1 - (1 - 2 * np.count_nonzero(ca != cb) / len(ca)) ** 2) / 2)
    result = dict(ones=sum(n for key, n in counts.items() if outcome_bit(key, kind, q)),
                  shots=shots, p1_est=p1, p1_exact=ideal, qubits=qc.num_qubits,
                  two_qubit_gates=sum(i.operation.num_qubits == 2 for i in isa.data),
                  depth=isa.depth(), seconds=seconds, p1_ideal=ideal,
                  backend=backend, pair=pair, family=family, q=int(q))
    if readout_cal:
        result["p1_est_cal"] = p1_from_counts(counts, kind, q, cal)
    if bootstrap_resamples:
        details = output[5]
        result.update(bootstrap_p1(counts, kind, q, details["calibration_counts"],
                                   resamples=bootstrap_resamples, seed=simulator_seed if simulator_seed is not None else seed))
        result["sampling_details"] = details
    return result


def _runtime_specs(specs, backend):
    """Validate the whole batch before contacting IBM or submitting anything."""
    normalized, circuits = [], []
    defaults = dict(pair="same", shots=4000, kind="ancilla", family="random",
                    method="diagonal", readout_cal=True, seed=None,
                    transpile_seed=None, simulator_seed=None, bootstrap_resamples=2000)
    for given in specs:
        unknown = set(given) - (set(defaults) | {"q"})
        if unknown:
            raise ValueError(f"unknown toy options: {sorted(unknown)}")
        s = dict(defaults, **given)
        for key, minimum in (("q", 1), ("shots", 1), ("bootstrap_resamples", 0)):
            value = s.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < minimum:
                raise ValueError(f"{key} must be an integer >= {minimum}")
            s[key] = int(value)
        if s["transpile_seed"] is None:
            s["transpile_seed"] = s["seed"]
        ca, cb = _toy_codewords(s["q"], s["pair"], s["family"], s["seed"])
        circuits.append(_swap_prepared(_sign_state_circuit(ca, s["method"]),
                                        _sign_state_circuit(cb, s["method"]), s["kind"]))
        s["p1_ideal"] = float((1 - (1 - 2*np.count_nonzero(ca != cb)/len(ca))**2)/2)
        s["backend"] = backend if isinstance(backend, str) else backend.name
        normalized.append(s)
    if not normalized:
        raise ValueError("specs must contain at least one toy circuit")
    if len({s["shots"] for s in normalized}) != 1:
        raise ValueError("one Runtime job requires the same shots for every spec")
    if len({s["simulator_seed"] for s in normalized}) != 1:
        raise ValueError("one Runtime job requires a common simulator_seed")
    return circuits, normalized


def run_batch(specs, backend, *, service=None, on_submitted=None, max_execution_time=179):
    """Run many toys and physical-wire readout calibrations in ONE Runtime job.

    Each spec is a dict of run() options except backend. Defaults match run(),
    except readout_cal=True and bootstrap_resamples=2000. All shots must match.
    backend accepts 'ibm:<device>', 'ibm:least_busy', or a BackendV2 (including
    FakeFez for offline local testing). on_submitted(job, manifest) runs BEFORE
    waiting for results, for durable job-ID storage. Its manifest contains PUB
    indices, physical wires and compiled costs for recovery without recompiling.
    The caller owns status polling when using that callback. No session is opened.
    """
    from datetime import datetime, timezone
    from time import perf_counter
    from ._execution import (runtime_backend, prepare_runtime_batch,
                             submit_runtime_batch, decode_runtime_batch)

    circuits, normalized = _runtime_specs(specs, backend)
    target = runtime_backend(backend, service)
    start = perf_counter()
    pubs, manifests = prepare_runtime_batch(circuits, normalized, target)
    job = submit_runtime_batch(pubs, target, normalized[0]["shots"],
                               max_execution_time=max_execution_time,
                               simulator_seed=normalized[0]["simulator_seed"])
    manifest = dict(job_id=job.job_id(), device=target.name,
                    date=datetime.now(timezone.utc).isoformat(),
                    circuits=manifests, pub_count=len(pubs))
    if on_submitted is not None:
        on_submitted(job, manifest)
    return decode_runtime_batch(job.result(), manifests, job_id=manifest["job_id"],
                                device=target.name, date=manifest["date"],
                                seconds=perf_counter()-start)
