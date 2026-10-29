"""Compare two fingerprints unit by unit with SWAP tests.

For each unit the SWAP test's ancilla reads 1 with probability p1 = (1 - overlap^2) / 2. Identical units give p1 = 0
and never read 1, so in strict mode a single 1 proves that the unit changed. The "exact" backend computes the overlap
exactly from the fingerprints and samples the shot outcomes with numpy, which is identical in distribution to running
noiseless SWAP-test circuits.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import DEFAULT_SHOTS, PERCEPTUAL_F_THRESHOLD, PERCEPTUAL_SHOTS
from .fingerprint import Fingerprint
from .theory import code_info, swap_test_p1


@dataclass
class Comparison:
    """Outcome of `compare`; every array has the fingerprints' grid shape. Unit index = row * cols + col."""

    mode: str
    backend: str
    shots: int
    grid: tuple[int, int]
    overlap: np.ndarray  # float64: exact overlap per unit
    p1: np.ndarray  # float64: (1 - overlap^2) / 2
    ones: np.ndarray  # int64: shots that read 1
    flagged: np.ndarray  # bool: unit judged changed
    tampered: bool  # any unit flagged
    changed_fraction: float  # flagged units / all units
    traces: dict[int, list[int]]  # unit -> per-shot outcomes (0/1) of the most suspicious units
    first_detection: dict[int, int | None]  # unit -> 1-based shot index of its first 1
    circuit_tiles: list[int]  # units run as real Qiskit circuits (empty for "exact")
    miss_bound: float | None  # strict with threshold=None only: (1 - p1_min)^shots

    def to_dict(self) -> dict:
        """JSON-safe copy: nested lists, Python bools/ints/floats, dict keys as str."""
        return {
            "mode": self.mode,
            "backend": self.backend,
            "shots": int(self.shots),
            "grid": [int(v) for v in self.grid],
            "overlap": self.overlap.tolist(),
            "p1": self.p1.tolist(),
            "ones": self.ones.tolist(),
            "flagged": self.flagged.tolist(),
            "tampered": bool(self.tampered),
            "changed_fraction": float(self.changed_fraction),
            "traces": {str(u): [int(v) for v in t] for u, t in self.traces.items()},
            "first_detection": {str(u): None if s is None else int(s) for u, s in self.first_detection.items()},
            "circuit_tiles": [int(u) for u in self.circuit_tiles],
            "miss_bound": None if self.miss_bound is None else float(self.miss_bound),
        }


def overlaps(a: Fingerprint, b: Fingerprint) -> np.ndarray:
    """Exact overlap <a|b> of every unit's pair of states, float64 array of shape `grid`.

    strict: 1 - 2 d / 2048 and perceptual: 1 - 2 d / 64, with d the Hamming distance of the sign bits;
    frqi: mean of cos(theta - theta') over all 64 positions, including 16 zero-angle padding positions.
    Identical units give exactly 1.0.
    """
    if a.mode != b.mode or a.version != b.version:
        raise ValueError(f"cannot compare fingerprints of different versions: {a.version!r} vs {b.version!r}")
    if a.mode == "frqi":
        ov = np.cos(a.data - b.data).mean(axis=1)
    else:  # strict and perceptual: +-1 amplitudes, so the overlap counts agreeing minus disagreeing signs
        d = (a.data != b.data).sum(axis=1)
        ov = 1.0 - 2.0 * d / a.data.shape[1]
    return ov.reshape(a.grid)


def compare(
    a: Fingerprint,
    b: Fingerprint,
    shots: int | None = None,
    backend: str = "exact",
    seed: int | None = None,
    threshold: float | None = None,
    trace_tiles: int = 4,
    kind: str = "ancilla",
) -> Comparison:
    """SWAP-test every unit of `a` against `b` with `shots` shots each and judge which units changed.

    Outcomes are drawn from np.random.default_rng(seed): first, one rng.random(shots) per traced unit (the
    `trace_tiles` units with the largest p1 > 0, most suspicious first; the first `trace_tiles` units if none has
    p1 > 0), then one rng.binomial(shots, p1) for all other units in index order.
    Decision: strict/frqi flag a unit if ones > 0, or if ones / shots > threshold when a threshold is given (for noisy
    backends); perceptual flags it if F = max(0, 1 - 2 ones / shots) < threshold (default PERCEPTUAL_F_THRESHOLD).
    shots=None uses the mode's budget: DEFAULT_SHOTS (32) for strict and frqi, PERCEPTUAL_SHOTS for perceptual.
    miss_bound applies only to strict mode with threshold=None (the default any-1 rule).
    For backend="aer", traced units use real Aer memory; other units use the
    binomial path. kind selects only Aer's SWAP test. Each traced unit uses
    seed_simulator=seed_transpiler=(seed + unit) modulo 2**32, if seeded.
    The default remains four traces (q=11 benchmark is below 20 seconds).
    """
    _check_backend(backend)
    if backend == "aer" and kind not in ("ancilla", "destructive"):
        raise ValueError("kind must be 'ancilla' or 'destructive'")
    if shots is None:
        shots = PERCEPTUAL_SHOTS if a.mode == "perceptual" else DEFAULT_SHOTS
    shots, trace_tiles = int(shots), int(trace_tiles)
    if shots < 1 or trace_tiles < 0:
        raise ValueError(f"need shots >= 1 and trace_tiles >= 0, got shots={shots}, trace_tiles={trace_tiles}")
    overlap = overlaps(a, b)
    p1 = swap_test_p1(overlap)
    flat_p1 = p1.reshape(-1)
    rng = np.random.default_rng(seed)

    traced = _most_suspicious(flat_p1, trace_tiles)
    ones = np.zeros(flat_p1.size, dtype=np.int64)
    traces: dict[int, list[int]] = {}
    first_detection: dict[int, int | None] = {}
    for u in traced:
        if backend == "aer":
            from .circuits import _run_unit_memory

            unit_seed = None if seed is None else (seed + u) % (2**32)
            outcomes = _run_unit_memory(a, b, u, shots, kind, unit_seed)
        else:
            outcomes = rng.random(shots) < flat_p1[u]
        traces[u] = outcomes.astype(int).tolist()
        ones[u] = int(outcomes.sum())
        hits = np.flatnonzero(outcomes)
        first_detection[u] = int(hits[0]) + 1 if hits.size else None
    rest = np.ones(flat_p1.size, dtype=bool)
    rest[traced] = False
    ones[rest] = rng.binomial(shots, flat_p1[rest])
    ones = ones.reshape(a.grid)

    if a.mode == "perceptual":
        f_hat = np.maximum(0.0, 1.0 - 2.0 * ones / shots)
        flagged = f_hat < (PERCEPTUAL_F_THRESHOLD if threshold is None else threshold)
    elif threshold is None:
        flagged = ones > 0
    else:
        flagged = ones / shots > threshold

    return Comparison(
        mode=a.mode,
        backend=backend,
        shots=shots,
        grid=tuple(a.grid),
        overlap=overlap,
        p1=p1,
        ones=ones,
        flagged=flagged,
        tampered=bool(flagged.any()),
        changed_fraction=float(flagged.mean()),
        traces=traces,
        first_detection=first_detection,
        circuit_tiles=traced if backend == "aer" else [],
        miss_bound=(1.0 - code_info()["p1_min"]) ** shots if a.mode == "strict" and threshold is None else None,
    )


def _most_suspicious(p1: np.ndarray, k: int) -> list[int]:
    """Up to k units with the largest p1 > 0 (ties: lower index first); the first k units if no unit has p1 > 0."""
    order = np.argsort(-p1, kind="stable")[:k]
    picked = [int(u) for u in order if p1[u] > 0]
    return picked if picked else list(range(min(k, p1.size)))


def _check_backend(backend: str) -> None:
    if backend in ("exact", "aer"):
        return
    if backend.startswith("aer-noisy:"):
        raise NotImplementedError(f"backend {backend!r} runs toy fingerprints only, via sp.toy.run (milestone C2, Darshan)")
    if backend.startswith("ibm:"):
        raise NotImplementedError(f"backend {backend!r} runs toy fingerprints only, via sp.toy.run (milestone C3, Darshan)")
    raise ValueError(f"unknown backend {backend!r}; expected 'exact', 'aer', 'aer-noisy:<FakeBackend>' or 'ibm:<device>'")
