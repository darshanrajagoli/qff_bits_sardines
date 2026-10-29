"""Core tests for swapprint v0.1 (milestone C0). Run `pytest -q`; skip the timing tests with `-m "not slow"`."""

from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import swapprint as sp
from swapprint import codes, encodings, synthetic, theory
from swapprint.config import CANON, PERCEPTUAL_F_THRESHOLD, PERCEPTUAL_SHOTS, PHASH_FLAT_SIGMA, STRICT_BITS, STRICT_M

REPO = Path(__file__).resolve().parents[1]
CHANGED_TILE = (128 // 4) * 64 + 128 // 4  # the strict/frqi unit holding pixel (128, 128)


@pytest.fixture(scope="module")
def art() -> np.ndarray:
    return synthetic.artwork(0)


@pytest.fixture(scope="module")
def fp_strict(art) -> sp.Fingerprint:
    return sp.fingerprint(art, "strict")


@pytest.fixture(scope="module")
def fp_strict_pixel(art) -> sp.Fingerprint:
    return sp.fingerprint(sp.edits.apply(art, "pixel"), "strict")


def reference_resize(a: np.ndarray) -> np.ndarray:
    """Independent implementation of the canonical resize, with 0/1 selection matrices instead of reduceat."""

    def selection(length: int) -> np.ndarray:
        b = (np.arange(CANON + 1) * length) // CANON
        s = np.zeros((CANON, length))
        for k in range(CANON):
            if length >= CANON:
                s[k, b[k] : b[k + 1]] = 1
            else:
                s[k, b[k]] = 1
        return s

    rows, cols = selection(a.shape[0]), selection(a.shape[1])
    sums = np.stack([rows @ a[:, :, ch].astype(np.float64) @ cols.T for ch in range(3)], axis=2).astype(np.int64)
    counts = (rows.sum(1)[:, None] * cols.sum(1)[None, :]).astype(np.int64)[:, :, None]
    return ((2 * sums + counts) // (2 * counts)).astype(np.uint8)


# ---------------------------------------------------------------- load_image


def test_load_image_256_is_bit_identical(art):
    out = sp.load_image(art)
    assert out.dtype == np.uint8 and out.shape == (256, 256, 3) and out.flags.c_contiguous
    assert np.array_equal(out, art) and out is not art
    assert np.array_equal(sp.load_image(out), out)


def test_load_image_sources_agree(art, tmp_path):
    buf = io.BytesIO()
    Image.fromarray(art).save(buf, format="PNG")
    png = buf.getvalue()
    path = tmp_path / "art.png"
    path.write_bytes(png)
    for src in (Image.fromarray(art), png, path, str(path), io.BytesIO(png)):
        assert np.array_equal(sp.load_image(src), art), type(src)


def test_downscale_of_constant_image_stays_constant():
    for shape in [(512, 512), (700, 300), (1000, 999), (257, 256)]:
        img = np.empty(shape + (3,), dtype=np.uint8)
        img[...] = (10, 128, 250)
        out = sp.load_image(img)
        assert out.shape == (256, 256, 3)
        assert (out == np.array([10, 128, 250], dtype=np.uint8)).all()


@pytest.mark.parametrize("shape", [(512, 512), (100, 600), (600, 100), (50, 50), (257, 255), (1000, 3), (300, 1)])
def test_resize_matches_reference(shape):
    img = np.random.default_rng(1).integers(0, 256, size=shape + (3,), dtype=np.uint8)
    out = sp.load_image(img)
    assert out.dtype == np.uint8 and out.shape == (256, 256, 3) and out.flags.c_contiguous
    assert np.array_equal(out, reference_resize(img))


def test_resize_rounds_half_up():
    img = np.zeros((512, 256, 3), dtype=np.uint8)
    img[1::2] = 1  # every output pixel averages a 0 and a 1: 0.5 rounds up to 1
    assert (sp.load_image(img) == 1).all()


def test_load_image_grey_alpha_and_exif():
    rgb = np.random.default_rng(2).integers(0, 256, size=(256, 512, 3), dtype=np.uint8)
    grey = rgb[:, :, 0]
    assert np.array_equal(sp.load_image(grey), sp.load_image(np.repeat(grey[:, :, None], 3, axis=2)))
    rgba = np.concatenate([rgb, np.full(rgb.shape[:2] + (1,), 7, dtype=np.uint8)], axis=2)
    assert np.array_equal(sp.load_image(rgba), sp.load_image(rgb))

    exif = Image.Exif()
    exif[0x0112] = 6  # orientation: rotate 90 degrees clockwise to display
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="PNG", exif=exif)
    assert np.array_equal(sp.load_image(buf.getvalue()), sp.load_image(np.rot90(rgb, k=-1)))


def test_load_image_rejects_bad_input():
    with pytest.raises(ValueError):
        sp.load_image(np.zeros((10, 10, 3), dtype=np.float64))
    with pytest.raises(ValueError):
        sp.load_image(np.zeros((10, 10, 2), dtype=np.uint8))
    with pytest.raises(TypeError):
        sp.load_image(42)


# ---------------------------------------------------------------- fingerprints


@pytest.mark.parametrize(
    "mode, q, grid, unit_px, shape, dtype, version",
    [
        ("strict", 11, (64, 64), 4, (4096, 2048), np.uint8, "swapprint-0.1/strict/q11/qff-sardines-2026"),
        ("perceptual", 6, (4, 4), 64, (16, 64), np.uint8, f"swapprint-0.1/perceptual/q6/r64/flat{PHASH_FLAT_SIGMA}"),
        ("frqi", 7, (64, 64), 4, (4096, 64), np.float64, "swapprint-0.1/frqi/q7/n64"),
    ],
)
def test_fingerprint_fields(art, mode, q, grid, unit_px, shape, dtype, version):
    fp = sp.fingerprint(art, mode)
    assert (fp.mode, fp.q, fp.grid, fp.unit_px, fp.version) == (mode, q, grid, unit_px, version)
    assert fp.data.shape == shape and fp.data.dtype == dtype and not fp.data.flags.writeable
    if dtype == np.uint8:
        assert set(np.unique(fp.data)) <= {0, 1}


def test_fingerprint_rejects_non_canonical(art):
    with pytest.raises(ValueError, match="load_image"):
        sp.fingerprint(art[:128])
    with pytest.raises(ValueError, match="load_image"):
        sp.fingerprint(art.astype(np.float32))
    with pytest.raises(ValueError):
        sp.fingerprint(art, "nope")


def test_generator_matrix_is_fixed():
    g = codes.generator_matrix()
    assert g.shape == (STRICT_BITS, STRICT_M) and g.dtype == np.uint8 and not g.flags.writeable
    stream = hashlib.shake_256(b"swapprint/v0.1/strict-code/qff-sardines-2026").digest(STRICT_BITS * STRICT_M // 8)
    assert np.array_equal(np.packbits(g), np.frombuffer(stream, dtype=np.uint8))


def test_code_is_linear_and_exact(art, fp_strict):
    rng = np.random.default_rng(3)
    x, y = rng.integers(0, 2, size=(2, 16, STRICT_BITS), dtype=np.uint8)
    assert np.array_equal(codes.encode(x ^ y), codes.encode(x) ^ codes.encode(y))
    msgs = np.vstack([x, np.ones((1, STRICT_BITS), np.uint8), np.zeros((1, STRICT_BITS), np.uint8)])
    exact = (msgs.astype(np.int64) @ codes.generator_matrix().astype(np.int64)) % 2
    assert np.array_equal(codes.encode(msgs), exact)
    # the contract's formula, (bits.astype(float32) @ G.astype(float32)) % 2, bit for bit on a whole image
    tile_bits = np.unpackbits(encodings.tile_values(art), axis=1)
    g32 = codes.generator_matrix().astype(np.float32)
    assert np.array_equal(fp_strict.data, ((tile_bits.astype(np.float32) @ g32) % 2).astype(np.uint8))


# ---------------------------------------------------------------- strict mode


def test_strict_identical_is_never_flagged(art, fp_strict):
    other = sp.fingerprint(art.copy(), "strict")
    assert other == fp_strict
    ov = sp.overlaps(fp_strict, other)
    assert ov.shape == (64, 64) and ov.dtype == np.float64 and (ov == 1.0).all()
    for seed in [None, *range(20)]:
        cmp = sp.compare(fp_strict, other, seed=seed)
        assert (cmp.p1 == 0).all() and (cmp.ones == 0).all() and not cmp.flagged.any()
        assert cmp.tampered is False and cmp.changed_fraction == 0.0
        assert list(cmp.traces) == [0, 1, 2, 3]  # nothing suspicious: trace the first units
        assert all(v is None for v in cmp.first_detection.values())


@pytest.mark.parametrize("delta", [1, -1])
def test_strict_catches_one_pixel_edit(art, fp_strict, delta):
    edited = sp.fingerprint(sp.edits.apply(art, "pixel", delta=delta), "strict")
    ov = sp.overlaps(fp_strict, edited).ravel()
    assert np.flatnonzero(ov < 1).tolist() == [CHANGED_TILE]
    assert abs(ov[CHANGED_TILE]) < 0.2
    detected = 0
    for seed in range(50):
        cmp = sp.compare(fp_strict, edited, shots=32, seed=seed)
        detected += cmp.tampered
        assert np.flatnonzero(cmp.flagged.ravel()).tolist() in ([], [CHANGED_TILE])
        assert list(cmp.traces) == [CHANGED_TILE]
    assert detected >= 49


def test_traces_agree_with_ones(fp_strict):
    other = sp.fingerprint(synthetic.artwork(5), "strict")  # every tile differs
    cmp = sp.compare(fp_strict, other, shots=40, seed=7, trace_tiles=6)
    assert len(cmp.traces) == 6
    flat_ones = cmp.ones.ravel()
    for u, trace in cmp.traces.items():
        assert len(trace) == 40 and set(trace) <= {0, 1}
        assert sum(trace) == flat_ones[u]
        first = cmp.first_detection[u]
        assert first == (trace.index(1) + 1 if 1 in trace else None)
    order = np.argsort(-cmp.p1.ravel(), kind="stable")[:6]
    assert list(cmp.traces) == order.tolist()


def test_compare_is_deterministic(fp_strict):
    other = sp.fingerprint(synthetic.artwork(5), "strict")
    a = sp.compare(fp_strict, other, seed=11)
    b = sp.compare(fp_strict, other, seed=11)
    c = sp.compare(fp_strict, other, seed=12)
    assert np.array_equal(a.ones, b.ones) and a.traces == b.traces and np.array_equal(a.flagged, b.flagged)
    assert not np.array_equal(a.ones, c.ones)


def test_threshold_rule(fp_strict):
    other = sp.fingerprint(synthetic.artwork(5), "strict")
    cmp = sp.compare(fp_strict, other, shots=32, seed=0, threshold=0.4)
    assert np.array_equal(cmp.flagged, cmp.ones / 32 > 0.4)
    assert 0 < cmp.changed_fraction < 1


def test_miss_bound(fp_strict, fp_strict_pixel, art):
    cmp = sp.compare(fp_strict, fp_strict_pixel, shots=32, seed=0)
    assert cmp.miss_bound == pytest.approx((1 - sp.code_info()["p1_min"]) ** 32)
    fp_frqi = sp.fingerprint(art, "frqi")
    assert sp.compare(fp_frqi, fp_frqi).miss_bound is None
    fp_perceptual = sp.fingerprint(art, "perceptual")
    assert sp.compare(fp_perceptual, fp_perceptual).miss_bound is None


def test_default_shots_follow_the_mode(fp_strict, art):
    assert sp.compare(fp_strict, fp_strict, seed=0).shots == sp.config.DEFAULT_SHOTS == 32
    fp_perceptual = sp.fingerprint(art, "perceptual")
    assert sp.compare(fp_perceptual, fp_perceptual, seed=0).shots == sp.config.PERCEPTUAL_SHOTS
    assert sp.compare(fp_perceptual, fp_perceptual, shots=100, seed=0).shots == 100


@pytest.mark.parametrize("threshold", [0.0, 0.4, 1.0])
def test_strict_threshold_has_no_miss_bound(fp_strict, fp_strict_pixel, threshold):
    cmp = sp.compare(fp_strict, fp_strict_pixel, threshold=threshold, seed=0)
    assert cmp.miss_bound is None and cmp.to_dict()["miss_bound"] is None


def test_to_dict_is_json(fp_strict, fp_strict_pixel):
    cmp = sp.compare(fp_strict, fp_strict_pixel, shots=32, seed=0)
    d = json.loads(json.dumps(cmp.to_dict()))
    assert d["tampered"] is True and d["grid"] == [64, 64] and d["circuit_tiles"] == []
    assert list(d["traces"]) == [str(CHANGED_TILE)] and isinstance(d["first_detection"][str(CHANGED_TILE)], int)
    assert np.array_equal(np.array(d["flagged"]), cmp.flagged) and np.array_equal(np.array(d["ones"]), cmp.ones)


def test_compare_refuses_mismatched_fingerprints(art, fp_strict):
    with pytest.raises(ValueError):
        sp.overlaps(fp_strict, sp.fingerprint(art, "frqi"))
    with pytest.raises(ValueError):
        sp.compare(fp_strict, sp.fingerprint(art, "perceptual"))


@pytest.mark.parametrize("mode, old_version", [
    ("perceptual", "swapprint-0.1/perceptual/q6/dz2.0"),
    ("frqi", "swapprint-0.1/frqi/q7"),
])
def test_compare_refuses_old_encoding_versions(art, mode, old_version):
    fp = sp.fingerprint(art, mode)
    with pytest.raises(ValueError, match="different versions"):
        sp.compare(fp, replace(fp, version=old_version))


def test_backends(fp_strict):
    for backend, milestone in [("aer", "C1"), ("aer-noisy:FakeBrisbane", "C2"), ("ibm:ibm_torino", "C3")]:
        with pytest.raises(NotImplementedError, match=milestone):
            sp.compare(fp_strict, fp_strict, backend=backend)
        with pytest.raises(NotImplementedError, match=milestone):
            sp.toy.run(2, backend=backend)
    with pytest.raises(ValueError):
        sp.compare(fp_strict, fp_strict, backend="qasm")
    for stub in [
        lambda: sp.circuits.state_circuit(fp_strict, 0),
        lambda: sp.circuits.swap_test(fp_strict, fp_strict, 0),
        lambda: sp.circuits.run_swap_test(fp_strict, fp_strict, 0),
        lambda: sp.circuits.example_circuit(),
        lambda: sp.circuits.example_circuit(q=3, kind="destructive"),
        lambda: sp.toy.run(2),
    ]:
        with pytest.raises(NotImplementedError, match="C1"):
            stub()


# ---------------------------------------------------------------- perceptual and frqi modes


def test_perceptual_identical_and_content_edit(art):
    fp = sp.fingerprint(art, "perceptual")
    ov = sp.overlaps(fp, sp.fingerprint(art.copy(), "perceptual"))
    assert ov.shape == (4, 4) and (ov == 1.0).all()
    spliced = sp.fingerprint(sp.edits.apply(art, "splice"), "perceptual")
    assert (sp.overlaps(fp, spliced) < 1).any()


def test_perceptual_decision_rule(art):
    fp = sp.fingerprint(art, "perceptual")
    other = sp.fingerprint(synthetic.artwork(5), "perceptual")
    cmp = sp.compare(fp, other, shots=32, seed=0)
    f_hat = np.maximum(0, 1 - 2 * cmp.ones / 32)
    assert np.array_equal(cmp.flagged, f_hat < PERCEPTUAL_F_THRESHOLD) and cmp.tampered
    assert not sp.compare(fp, other, shots=32, seed=0, threshold=0.0).flagged.any()
    assert not sp.compare(fp, fp, seed=0).tampered


def test_perceptual_jpeg90_and_text_at_recommended_settings(art):
    fp = sp.fingerprint(art, "perceptual")
    jpeg = sp.fingerprint(sp.edits.jpeg(art, quality=90), "perceptual")
    text = sp.fingerprint(sp.edits.text(art), "perceptual")
    # Most shot seeds tolerate a JPEG re-save of the standard synthetic artwork.
    assert sum(sp.compare(fp, jpeg, shots=PERCEPTUAL_SHOTS, seed=s).tampered for s in range(50)) <= 2
    assert all(sp.compare(fp, text, shots=PERCEPTUAL_SHOTS, seed=s).tampered for s in range(20))
    # Also check a majority of independently generated artworks, without selecting convenient seeds.
    tolerated = 0
    for seed in range(32):
        img = synthetic.artwork(seed)
        a = sp.fingerprint(img, "perceptual")
        b = sp.fingerprint(sp.edits.jpeg(img, quality=90), "perceptual")
        tolerated += not sp.compare(a, b, shots=PERCEPTUAL_SHOTS, seed=seed).tampered
    assert tolerated >= 24


def test_perceptual_matches_scalar_reference(art):
    from scipy.fft import dctn

    expected = np.zeros((16, 64), np.uint8)
    for row in range(4):
        for col in range(4):
            region = art[row * 64 : (row + 1) * 64, col * 64 : (col + 1) * 64].astype(np.int64)
            y = (region @ np.array([299, 587, 114]) + 500) // 1000
            averaged = sum(y[dy::2, dx::2].astype(np.float64) for dy in range(2) for dx in range(2)) / 4
            ac = dctn(averaged, type=2, norm="ortho")[:8, :8].ravel()[1:]
            if np.sqrt(np.mean(ac**2)) >= PHASH_FLAT_SIGMA:
                expected[row * 4 + col, 1:] = ac > np.median(ac)
    assert np.array_equal(sp.fingerprint(art, "perceptual").data, expected)


@pytest.mark.parametrize("value", [0, 128, 255])
def test_perceptual_flat_regions(value):
    img = np.full((256, 256, 3), value, dtype=np.uint8)
    assert not sp.fingerprint(img, "perceptual").data.any()
    # Mild grain must not turn a flat region into an arbitrary median-split hash.
    noise = np.random.default_rng(0).integers(-3, 4, size=img.shape)
    noisy = np.clip(img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    assert not sp.fingerprint(noisy, "perceptual").data.any()


def test_frqi_barely_sees_one_value_edit(art):
    fp = sp.fingerprint(art, "frqi")
    ov = sp.overlaps(fp, sp.fingerprint(sp.edits.apply(art, "pixel"), "frqi")).ravel()
    assert np.flatnonzero(ov < 1).tolist() == [CHANGED_TILE]
    assert 0.99999 < ov[CHANGED_TILE] < 1
    assert (sp.overlaps(fp, fp) == 1.0).all()
    expected_overlap = (63 + math.cos(math.pi / 510)) / 64
    expected_p1 = (1 - expected_overlap**2) / 2
    actual_p1 = theory.swap_test_p1(ov[CHANGED_TILE])
    assert actual_p1 == pytest.approx(expected_p1, rel=1e-9, abs=1e-16)


def test_frqi_positions_and_state_overlap(art):
    fp = sp.fingerprint(art, "frqi")
    other = sp.fingerprint(sp.edits.patch(art, size=12), "frqi")
    assert (fp.data[:, 48:] == 0).all() and (other.data[:, 48:] == 0).all()
    assert np.array_equal(fp.data[:, :48], (np.pi / 2) * encodings.tile_values(art).astype(np.float64) / 255)
    # Explicit amplitudes of the 7-qubit state, independent of the cosine-difference overlap formula.
    a = np.stack([np.cos(fp.data), np.sin(fp.data)], axis=-1).reshape(4096, 128) / 8
    b = np.stack([np.cos(other.data), np.sin(other.data)], axis=-1).reshape(4096, 128) / 8
    assert np.allclose(np.sum(a**2, axis=1), 1, atol=1e-15, rtol=0)
    assert np.allclose(sp.overlaps(fp, other).ravel(), np.sum(a * b, axis=1), atol=1e-15, rtol=0)


# ---------------------------------------------------------------- edits


@pytest.mark.parametrize("name", sorted(sp.edits.REGISTRY))
def test_registry_edit_is_pure(art, name):
    before = art.copy()
    out = sp.edits.apply(art, name)
    assert out is not art and out.shape == (256, 256, 3) and out.dtype == np.uint8
    assert np.array_equal(art, before), "edit modified its input"
    changed = not np.array_equal(out, art)
    assert changed == (name != "identity")
    assert sp.edits.REGISTRY[name].category in {"control", "imperceptible", "benign", "content", "different"}


def test_pixel_and_lsb_always_change():
    img = np.full((256, 256, 3), 255, dtype=np.uint8)
    assert sp.edits.pixel(img)[128, 128, 0] == 254  # +1 would clip, so it goes -1
    bits = np.unpackbits(np.frombuffer(b"QFF", dtype=np.uint8))
    img[0, : bits.size, 2] = 254 | bits  # the payload is already hidden there
    out = sp.edits.lsb(img)
    assert (out != img).sum() == 1 and out[0, 0, 2] != img[0, 0, 2]
    assert not np.array_equal(sp.edits.lsb(np.zeros((256, 256, 3), np.uint8)), np.zeros((256, 256, 3), np.uint8))


def test_edit_errors(art):
    with pytest.raises(ValueError):
        sp.edits.apply(art, "nope")
    with pytest.raises(ValueError):
        sp.edits.apply(art, "patch", y=250, size=10)
    with pytest.raises(TypeError):
        sp.edits.splice(art)  # the plain function needs a donor


# ---------------------------------------------------------------- files and theory


@pytest.mark.parametrize("mode", ["strict", "perceptual", "frqi"])
def test_save_load_roundtrip(art, tmp_path, mode):
    fp = sp.fingerprint(art, mode)
    path = tmp_path / f"{mode}.fp"
    sp.save_fingerprint(fp, path)
    back = sp.load_fingerprint(path)
    assert back == fp and back.data.dtype == fp.data.dtype and not back.data.flags.writeable
    assert isinstance(back.grid, tuple) and isinstance(back.q, int)
    buf = io.BytesIO()
    sp.save_fingerprint(fp, buf)
    buf.seek(0)
    assert sp.load_fingerprint(buf) == fp


def test_code_info():
    info = sp.code_info()
    assert set(info) == {"n", "m", "rate", "seed", "d_min_guaranteed", "overlap_max", "p1_min", "failure_prob", "note"}
    assert (info["n"], info["m"], info["rate"], info["seed"]) == (384, 2048, 0.1875, "qff-sardines-2026")
    assert info["p1_min"] > 0.3
    assert info["overlap_max"] == 1 - 2 * info["d_min_guaranteed"] / 2048
    assert info["p1_min"] == (1 - info["overlap_max"] ** 2) / 2
    json.dumps(info)


def test_code_info_matches_scipy_binomial():
    from scipy.stats import binom

    m, n = STRICT_M, STRICT_BITS
    d = np.arange(m // 2 + 1)
    ref = binom.logcdf(d, m, 0.5)  # -inf, or imprecise, where the CDF underflows below ~1e-300
    ours = theory.log_binom_half_cdf(m)[: m // 2 + 1]
    normal = ref > -690
    assert normal.sum() > 700 and np.allclose(ours[normal], ref[normal], rtol=1e-10, atol=0)
    for failure in (1e-3, 1e-6, 1e-9, 1e-12):
        largest = np.flatnonzero((n + 1) * math.log(2) + ref <= math.log(failure))[-1]
        assert sp.code_info(failure)["d_min_guaranteed"] == largest + 1


def test_shots_needed():
    assert sp.shots_needed(miss=0.5, p1=0.5) == 1
    assert sp.shots_needed(miss=1e-6, p1=0.5) == 20
    assert (1 - 0.37) ** sp.shots_needed(1e-6, 0.37) <= 1e-6 < (1 - 0.37) ** (sp.shots_needed(1e-6, 0.37) - 1)
    with pytest.raises(ValueError):
        sp.shots_needed(1e-6, 0.0)


def test_import_is_light_and_qiskit_free():
    code = "import sys, swapprint; print('qiskit' in sys.modules, 'scipy' in sys.modules)"
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=REPO)
    assert run.stdout.split() == ["False", "False"]


# ---------------------------------------------------------------- timing


@pytest.mark.slow
def test_timing(art, fp_strict, fp_strict_pixel):
    t = time.perf_counter()
    sp.fingerprint(art, "strict")
    assert time.perf_counter() - t < 2.0
    t = time.perf_counter()
    sp.compare(fp_strict, fp_strict_pixel, shots=32, seed=0)
    assert time.perf_counter() - t < 0.5
