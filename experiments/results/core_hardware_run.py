"""C3 hardware collection/recovery. Run with the repo .venv Python, UTF-8 output.

--submit authorizes the first job only; an existing job manifest recovers that
job unless an exact failed ID is explicitly replaced. No credentials are read
directly or included in any artifact.
Run from the repo root: python experiments/results/core_hardware_run.py --submit
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
RESULTS = ROOT / "experiments/results"
JOB = RESULTS / "core_hardware_job.json"
INSTANCE = os.environ.get("QISKIT_IBM_INSTANCE")
DEVICES = {"ibm_fez", "ibm_kingston", "ibm_marrakesh"}


def save(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def design():
    return [dict(q=q, pair=pair, family=family, kind=kind, shots=4000,
                 seed=2026, transpile_seed=7, bootstrap_resamples=2000,
                 readout_cal=True)
            for q in (1, 2, 3)
            for family, pair in ([("random", p) for p in ("same", "near", "orthogonal")
                                   if q >= 2 or p != "near"] +
                                  ([("hadamard", "orthogonal")] if q == 2 else []))
            for kind in ("ancilla", "destructive")]


def properties_snapshot(backend):
    import numpy as np
    props = backend.properties()
    readout = [p.value for qs in props.qubits for p in qs if p.name == "readout_error"]
    twoq = [p.value for g in props.gates if len(g.qubits) == 2
            for p in g.parameters if p.name == "gate_error"]
    return dict(date=props.last_update_date.isoformat(),
                median_readout_error=float(np.median(readout)) if readout else None,
                median_two_qubit_error=float(np.median(twoq)) if twoq else None,
                readout_error_count=len(readout), two_qubit_error_count=len(twoq))


def account():
    from qiskit_ibm_runtime import QiskitRuntimeService
    # SDK exception strings may contain request details. Suppress them completely.
    logging.getLogger("qiskit_ibm_runtime").setLevel(logging.CRITICAL)
    end = time.monotonic() + 40*60
    while True:
        try:
            return QiskitRuntimeService()
        except Exception:
            print("waiting for saved IBM account", flush=True)
            if time.monotonic() >= end:
                return None
            time.sleep(min(60, max(0, end-time.monotonic())))


def collect(submit=False, replace_failed_job=None):
    from swapprint.toy import _runtime_specs
    from swapprint._execution import (prepare_runtime_batch, estimate_runtime_seconds,
                                      submit_runtime_batch, decode_runtime_batch)
    service = account()
    if service is None:
        (RESULTS / "core_hardware_SUMMARY.md").write_text(
            "Device: none; saved IBM account did not load within 40 minutes.\n"
            "Job ID: none; no hardware job submitted.\n"
            "Headline: no hardware p1 measurements; implementation and local tests only.\n"
            "QPU seconds used: 0.\n"
            "Status: BLOCKED C3 — saved IBM account unavailable after 40 minutes; "
            "batch execution and offline tests ready.\n", encoding="utf-8")
        return False
    if replace_failed_job is not None:
        prior = json.loads(JOB.read_text(encoding="utf-8"))
        if prior.get("job_id") != replace_failed_job:
            raise ValueError("replacement must name the exact failed job")
        failed = service.job(replace_failed_job)
        if failed.status() != "ERROR":
            raise ValueError("replacement is restricted to a confirmed failed job")
        prior.update(status="ERROR", failure="IBM server rejected QPY 18; no measurement results",
                     usage=failed.metrics().get("usage", {}), qpu_seconds=failed.usage())
        save(RESULTS / "core_hardware_failed_job.json", prior)
        # Keep the original job-ID record until the replacement is accepted.
        replacing = True
    else:
        replacing = False
    if JOB.exists() and not replacing:
        manifest = json.loads(JOB.read_text(encoding="utf-8"))
        if not manifest.get("job_id"):
            raise RuntimeError("existing submission record needs manual recovery; do not resubmit")
        job = service.job(manifest["job_id"])
    else:
        if not submit:
            raise RuntimeError("no job to recover; first submission requires --submit")
        backends = service.backends(instance=INSTANCE)
        print("\n".join(sorted(b.name for b in backends)), flush=True)
        candidates = [(b, b.status()) for b in backends if b.name in DEVICES]
        candidates = [(b, s) for b, s in candidates if s.operational and s.status_msg == "active"]
        if not candidates:
            raise RuntimeError("no allocated active QPU")
        backend, status = min(candidates, key=lambda item: item[1].pending_jobs)
        print(f"{backend.name}: {status.pending_jobs} pending jobs", flush=True)
        circuits, specs = _runtime_specs(design(), "ibm:" + backend.name)
        pubs, manifests = prepare_runtime_batch(circuits, specs, backend)
        shots = 4000
        estimated = estimate_runtime_seconds(pubs, backend, shots)
        if estimated >= 180:
            shots = 2000
            for m in manifests:
                m["shots"] = shots
            estimated = estimate_runtime_seconds(pubs, backend, shots)
        if estimated >= 180:
            raise RuntimeError("even 2000 shots exceed the 3-minute planning budget")
        print(f"{len(manifests)} toys + {len(pubs)-len(manifests)} calibration PUBs; "
              f"{shots} shots; conservative estimate {estimated:.2f} QPU seconds; cap 179 seconds", flush=True)
        manifest = dict(job_id=None, device=backend.name,
                        date=datetime.now(timezone.utc).isoformat(), circuits=manifests,
                        pub_count=len(pubs), shots=shots, estimated_qpu_seconds=estimated,
                        max_execution_time=179, backend_properties=properties_snapshot(backend),
                        runtime_version="0.51.0", sampler="qiskit_ibm_runtime.executor_sampler.Sampler",
                        estimation_method="sum instruction durations + reset + default rep_delay; 2s overhead per PUB",
                        options=dict(twirling=False, dynamical_decoupling=False))
        manifest["transport_schema"] = "v1.1 (QPY <=17 compatibility for Runtime 0.51.0)"
        if replacing:
            manifest["replaces_failed_job"] = replace_failed_job
        # Preflight record also prevents automatic duplicate submission if a crash
        # occurs after the server accepts a job but before the ID is returned.
        save(JOB, manifest)
        job = submit_runtime_batch(pubs, backend, shots, max_execution_time=179)
        manifest["job_id"] = job.job_id()
        save(JOB, manifest)  # FIRST action after obtaining the ID; no network queries.
        print(f"job_id: {manifest['job_id']}", flush=True)
    deadline = time.monotonic() + 3*60*60
    while True:
        try:
            status = job.status()
            print(str(status), flush=True)
        except Exception:
            print("status unavailable", flush=True)
            status = None
        if status in ("DONE", "ERROR", "CANCELLED"):
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("3-hour polling limit reached; recover with saved job ID")
        # Two short sleeps keep the process interruptible while polling every 2m.
        time.sleep(60)
        time.sleep(60)
    if status != "DONE":
        manifest["status"] = status
        manifest["error"] = job.error_message()
        manifest["usage"] = job.metrics().get("usage", {})
        manifest["qpu_seconds"] = job.usage()
        save(JOB, manifest)
        (RESULTS / "core_hardware_SUMMARY.md").write_text(
            f"Device: {manifest['device']}; submission failed, no toy-state measurements returned.\n"
            f"Job ID: {manifest['job_id']} ({status}).\n"
            f"Exact IBM error:\n{manifest['error']}\n"
            "Diagnosis: the client-side Sampler was submitted through Runtime 0.51.0's built-in "
            "v1.1 executor transport, which serializes QPY 17; local serialization and circuit "
            "round-trip tests passed. The server rejection above prevents a hardware result. "
            "No further submission is authorized.\n"
            f"QPU seconds: final reported {manifest['qpu_seconds']}; usage details {manifest['usage']}.\n",
            encoding="utf-8")
        return False
    result = job.result()
    # Preserve measurements before optional metrics queries, plotting or editing.
    rows = decode_runtime_batch(result, manifest["circuits"], job_id=manifest["job_id"],
                                device=manifest["device"], date=manifest["date"])
    output = dict(manifest, status="DONE", circuits=rows,
                  interval_method="95% percentile parametric bootstrap; 2000 joint test/calibration resamples; conditional shot noise only",
                  qpu_seconds=None, usage_status="pending")
    save(RESULTS / "core_hardware.json", output)
    metrics = job.metrics()
    output["usage"] = metrics.get("usage", {})
    output["timestamps"] = metrics.get("timestamps", {})
    output["qpu_seconds"] = job.usage()
    output["usage_status"] = output["usage"].get("status", "unknown")
    # Use execution date if available; submission time remains in JOB.
    executed = output["timestamps"].get("running") or manifest["date"]
    output["date"] = executed
    for row in rows:
        row["date"] = executed
    save(RESULTS / "core_hardware.json", output)
    columns = ("device date job_id q pair family kind shots ones p1_raw p1_raw_lo p1_raw_hi "
               "p1_cal p1_cal_lo p1_cal_hi p1_ideal two_qubit_gates depth raw_counts physical_qubits").split()
    with (RESULTS / "core_hardware.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row, raw_counts=json.dumps(row["raw_counts"], sort_keys=True),
                                 physical_qubits=json.dumps(row["physical_qubits"])))
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--replace-failed-job", help="exact failed job ID; requires explicit user approval")
    args = parser.parse_args()
    try:
        completed = collect(args.submit, args.replace_failed_job)
    except Exception as exc:
        # Never expose SDK exception text, request headers, account objects, etc.
        print(f"collection stopped ({type(exc).__name__}); recover using saved manifest", flush=True)
        sys.exit(1)
    sys.exit(0 if completed else 2)
