"""SwapPrint: quantum fingerprints for digital art, checked with a SWAP test.

    streamlit run app/streamlit_app.py --server.headless true
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # Streamlit runs scripts off the main thread; the macOS GUI backend crashes there

import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from streamlit_image_coordinates import streamlit_image_coordinates  # noqa: E402

import core  # noqa: E402
from certificate import make_certificate  # noqa: E402
import swapprint as sp  # noqa: E402

st.set_page_config(page_title="SwapPrint", page_icon="🔍", layout="wide")

AER_ENABLED = os.environ.get("SWAPPRINT_NO_AER", "") != "1"
ACCENT_HEX = "#E841D6"
CANON = sp.config.CANON
IST = timezone(timedelta(hours=5, minutes=30), "IST")

st.markdown(
    f"""
<style>
.block-container {{padding-top: 2rem; max-width: 1280px;}}
.verdict {{font-size: 2.6rem; font-weight: 800; letter-spacing: .02em; line-height: 1.1; margin: .2rem 0 .3rem 0;}}
.verdict.hit {{color: {ACCENT_HEX};}}
.verdict.miss {{color: #C9CDD6;}}
.fine {{color: #9AA0AB; font-size: .85rem;}}
.lead {{font-size: 1.1rem;}}
.shots {{display: flex; flex-wrap: wrap; gap: 4px; margin: .4rem 0 .6rem 0;}}
.shot {{width: 22px; height: 22px; border-radius: 4px; background: #3A3F4B; color: #C9CDD6; font-size: 11px;
        display: flex; align-items: center; justify-content: center; font-family: monospace;}}
.shot.one {{background: {ACCENT_HEX}; color: white; font-weight: 700;}}
.shot.first {{outline: 3px solid white;}}
.box {{border: 1px solid #3A3F4B; border-radius: 10px; padding: .9rem 1.1rem; background: #1A1D24;}}
</style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------- cached work


@st.cache_resource(max_entries=24, show_spinner=False)
def fingerprint(img_sha: str, mode: str, _img: np.ndarray) -> sp.Fingerprint:
    return sp.fingerprint(_img, mode)


def fp_of(img: np.ndarray, mode: str) -> sp.Fingerprint:
    return fingerprint(core.sha(img), mode, img)


@st.cache_resource(show_spinner=False)
def gallery():
    return core.gallery()


@st.cache_resource(max_entries=32, show_spinner=False)
def artwork(file: str) -> np.ndarray:
    img = core.load_artwork(file)
    img.setflags(write=False)
    return img


@st.cache_resource(max_entries=8, show_spinner=False)
def fingerprint_npz(img_sha: str, mode: str, _fp: sp.Fingerprint) -> bytes:
    buf = io.BytesIO()
    sp.save_fingerprint(_fp, buf)
    return buf.getvalue()


ASSETS = Path(__file__).resolve().parent / "assets"


def show_toy_circuit(kind: str) -> None:
    """sp.circuits.example_circuit(q=2, kind) pre-rendered by app/make_assets.py: no Qiskit circuit in this process."""
    png = ASSETS / f"swap_test_q2_{kind}.png"
    if png.exists():
        st.image(str(png), output_format="PNG", width="stretch")
    else:
        st.caption("Circuit drawing missing: run python app/make_assets.py")


@st.cache_data(show_spinner=False)
def frqi_vs_strict() -> dict:
    """The quickstart's numbers: a one-value pixel edit on the synthetic artwork, through strict and FRQI."""
    img = sp.synthetic.artwork(seed=0)
    edit = sp.edits.apply(img, "pixel")
    out = {}
    for mode in ("strict", "frqi"):
        ov = sp.overlaps(sp.fingerprint(img, mode), sp.fingerprint(edit, mode))
        p1 = float(((1 - ov**2) / 2).max())
        out[mode] = dict(overlap=float(ov.min()), p1=p1, first=1 / p1, need99=sp.shots_needed(0.01, p1))
    return out


def safe(fn):
    """Run a UI section; show a friendly message instead of a traceback."""
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Something went wrong here ({type(exc).__name__}). Try Reset, or another artwork.")
            if os.environ.get("SWAPPRINT_DEBUG"):
                st.exception(exc)
    return wrapped


# ---------------------------------------------------------------- state

ss = st.session_state
ss.setdefault("history", [])
ss.setdefault("surprises", 0)
ss.setdefault("game", None)  # {"truth": (y, x), "guess": (y, x) | None, "revealed": bool}
ss.setdefault("loc", (128, 128))
ss.setdefault("verify", None)
ss.setdefault("aer", None)
ss.setdefault("aer_pick", None)


def reset_edits():
    ss.history = []
    ss.game = None
    ss.verify = None
    ss.aer = None
    ss.aer_pick = None


def new_click(key: str, click) -> bool:
    """The component keeps returning its last click on every rerun: only a new click counts."""
    if not click:
        return False
    stamp = (click.get("unix_time"), click.get("x"), click.get("y"))
    if ss.get(f"_last_{key}") == stamp:
        return False
    ss[f"_last_{key}"] = stamp
    return True


def click_to_canon(click) -> tuple[int, int]:
    w = click.get("width") or 512
    h = click.get("height") or 512
    return (min(CANON - 1, max(0, int(click["y"] * CANON / h))), min(CANON - 1, max(0, int(click["x"] * CANON / w))))


# ---------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown("## SwapPrint")
    st.caption("Quantum fingerprints for digital art, checked with a SWAP test")

    arts = gallery()
    options = [a.file for a in arts] + ["__synthetic__", "__upload__"]
    labels = {a.file: (f"{a.title} · {a.artist}" if a.artist and a.artist != "team sardines" else f"{a.title} (generated)")
              for a in arts}
    labels["__synthetic__"] = "Synthetic painting (pick a seed)"
    labels["__upload__"] = "Upload your own image…"
    default_art = "hokusai_great_wave.png" if "hokusai_great_wave.png" in options else options[0]
    choice = st.selectbox("Artwork", options, index=options.index(default_art), format_func=labels.get)

    base, source_note = None, ""
    if choice == "__upload__":
        up = st.file_uploader("PNG, JPEG, WebP, TIFF or BMP", type=["png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"])
        if up is not None:
            try:
                base, notes = core.load_upload(up.getvalue())
                source_note = f"{up.name}" + (f" ({'; '.join(notes)})" if notes else "")
            except ValueError as exc:
                st.warning(str(exc))
        if base is None:
            st.info("No upload yet: showing the synthetic painting.")
    if choice == "__synthetic__":
        syn_seed = st.number_input("Painting seed", 0, 9999, 0, 1)
        base, source_note = sp.synthetic.artwork(seed=int(syn_seed)), f"sp.synthetic.artwork(seed={int(syn_seed)})"
    if base is None and choice not in ("__upload__", "__synthetic__"):
        base, source_note = artwork(choice), labels[choice]
    if base is None:
        base, source_note = sp.synthetic.artwork(seed=0), "sp.synthetic.artwork(seed=0)"

    base_sha = core.sha(base)
    if ss.get("base_sha") != base_sha:
        ss.base_sha = base_sha
        reset_edits()

    mode = st.radio("Encoding", core.MODES, format_func=core.MODE_LABEL.get, horizontal=False,
                    help="strict: any change at all · perceptual: visible content only · frqi: the textbook baseline")
    if mode == "perceptual":
        shots = st.slider("Shots per region", 256, 16384, int(sp.config.PERCEPTUAL_SHOTS), 256, key="shots_p",
                          help="Perceptual mode estimates an overlap, so it needs many shots.")
    else:
        shots = st.slider("Shots per tile", 1, 256, int(sp.config.DEFAULT_SHOTS), 1, key=f"shots_{mode}",
                          help="Strict mode waits for a single 1: a few dozen shots are plenty.")
    seed = int(st.number_input("Seed", 0, 2**31 - 1, 0, 1, help="Fixes the random shot outcomes and the hidden game spot."))
    st.divider()
    st.caption(f"swapprint {sp.__version__} · exact backend = analytical sampler, identical in distribution to a "
               f"noiseless SWAP-test circuit on each unit")

edited = core.replay(base, ss.history)
edited_sha = core.sha(edited)
game = ss.game
game_on = bool(game and not game["revealed"])

st.markdown("# SwapPrint")
st.markdown('<div class="lead">Every 4×4 patch of an artwork gets an 11-qubit quantum fingerprint. A SWAP test '
            'compares fingerprints: an untouched patch never fires, a changed patch fires about half the time.</div>',
            unsafe_allow_html=True)

tabs = st.tabs(["1 · Fingerprint", "2 · Tamper", "3 · Verify", "How it works", "Results"])


# ---------------------------------------------------------------- 1 · Fingerprint


@safe
def tab_fingerprint():
    info = sp.code_info()
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.image(core.upscale(base, 768), caption=f"Canonical 256×256 image · {source_note}", output_format="PNG", width="stretch")
    with right:
        st.markdown("### What gets fingerprinted")
        st.markdown(
            f"- **{sp.config.STRICT_GRID**2:,} tiles × {sp.config.STRICT_Q} qubits.** Each 4×4 tile = "
            f"{info['n']} bits → {info['m']:,}-bit codeword → {sp.config.STRICT_Q}-qubit state.\n"
            f"- The code is a public pseudo-random linear [{info['m']}, {info['n']}] code (seed `{info['seed']}`). "
            f"Any change to a tile flips about half of its codeword's signs.\n"
            f"- Heuristic guarantee: minimum distance ≥ {info['d_min_guaranteed']}, so every changed tile has "
            f"p1 ≥ {info['p1_min']:.3f}, and {sp.shots_needed(1e-6, info['p1_min'])} shots miss it with "
            f"probability ≤ 10⁻⁶.\n"
            f"- Perceptual mode: {sp.config.PERCEPTUAL_GRID**2} regions of 64×64 px, a 64-bit pHash each, "
            f"{sp.config.PERCEPTUAL_Q} qubits.")
        st.caption(info["note"])

    st.markdown("### Fingerprint mosaic")
    st.markdown("Each tile drawn in a colour taken from the first 24 bits of its codeword. It looks like noise, and "
                "that is the point: change one pixel and its tile's codeword changes in about half its bits, so the tile almost always jumps to a completely different colour.")
    fa, fb = fp_of(base, "strict"), fp_of(edited, "strict")
    changed = (fa.data != fb.data).any(axis=1).reshape(fa.grid)
    c1, c2 = st.columns(2, gap="large")
    c1.image(core.mosaic_image(fa, 420), caption="Original's mosaic", output_format="PNG", width="stretch")
    n_changed = int(changed.sum())
    if not ss.history:
        c2.info("Make an edit in **2 · Tamper** to see the edited image's mosaic here.")
    elif game_on:
        c2.info("Hidden while the spot-the-edit game runs: the mosaic would give the answer away.")
    else:
        c2.image(core.mosaic_image(fb, 420, changed), output_format="PNG", width="stretch",
                 caption=f"Edited image's mosaic: {n_changed:,} of {changed.size:,} tiles have a different codeword"
                         + (" (ringed)" if 0 < n_changed <= 60 else ""))

    st.markdown("### Register this artwork")
    fp = fp_of(base, mode)
    data = fingerprint_npz(base_sha, mode, fp)
    st.download_button(f"Download the {core.MODE_LABEL[mode]} fingerprint (.npz, {len(data) / 1024:,.0f} KiB)", data,
                       file_name=f"swapprint_{mode}_{base_sha[:8]}.npz", mime="application/octet-stream")
    if mode == "strict":
        st.caption("Integrity, not secrecy: the strict code has full rank, so anyone holding this file can decode the "
                   "canonical image from it. Check a file against it in **3 · Verify**, without the original.")
    elif mode == "perceptual":
        st.caption("A perceptual fingerprint reveals only a coarse 64-bit hash per region.")
    else:
        st.caption("An FRQI fingerprint stores the pixel values as angles: it reveals the image.")


# ---------------------------------------------------------------- 2 · Tamper


@safe
def tab_tamper():
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("**Click the image to choose where to edit**")
        click = streamlit_image_coordinates(core.upscale(edited, 768), key="tamper-click", width="stretch")
        if new_click("tamper", click):
            ss.loc = click_to_canon(click)
        y, x = ss.loc
        st.caption(f"Chosen location: row {y}, column {x} (canonical pixels)")
    with right:
        st.markdown("**Edit tools**")
        name = st.selectbox("Tool", list(core.TOOLS), format_func=lambda n: core.TOOLS[n][0], key="tool")
        step = None
        if name == "pixel":
            ch = st.radio("Channel", [0, 1, 2], format_func=lambda c: "RGB"[c], horizontal=True)
            delta = st.radio("Change", [1, -1], format_func=lambda d: f"{d:+d}", horizontal=True)
            step = {"name": "pixel", "params": {"y": y, "x": x, "channel": ch, "delta": delta}}
        elif name == "set_pixel":
            rgb = _rgb(st.color_picker("Colour", "#FF2020"))
            step = {"name": "set_pixel", "params": {"y": y, "x": x, "rgb": rgb}}
        elif name == "patch":
            size = st.slider("Patch size (px)", 1, 32, 6)
            rgb = _rgb(st.color_picker("Colour", "#FF2020"))
            py, px = core.clamp_box(y, x, size)
            step = {"name": "patch", "params": {"y": py, "x": px, "size": size, "rgb": rgb}}
        elif name == "text":
            s = st.text_input("Text", "FAKE", max_chars=24) or "FAKE"
            ty, tx = core.clamp_box(y, x, 12)
            step = {"name": "text", "params": {"s": s, "y": ty, "x": tx}}
        elif name == "copy_move":
            size = st.slider("Square size (px)", 4, 64, 24)
            dy = st.slider("Move down by (px)", -128, 128, 40)
            dx = st.slider("Move right by (px)", -128, 128, 40)
            src = core.clamp_box(y, x, size)
            dst = core.clamp_box(src[0] + dy, src[1] + dx, size)
            step = {"name": "copy_move", "params": {"src": list(src), "dst": list(dst), "size": size}}
        elif name == "splice":
            donors = [a.file for a in gallery() if a.file != choice] or [a.file for a in gallery()]
            donor = st.selectbox("Donor artwork", donors, format_func=lambda f: next(a.title for a in gallery() if a.file == f))
            size = st.slider("Square size (px)", 8, 128, 48)
            sy, sx = core.clamp_box(y, x, size)
            step = {"name": "splice", "params": {"donor_file": donor, "y": sy, "x": sx, "size": size}}
        elif name == "lsb":
            msg = st.text_input("Message to hide", "QFF", max_chars=64) or "QFF"
            step = {"name": "lsb", "params": {"payload": msg, "channel": 2}}
        elif name == "brightness":
            step = {"name": "brightness", "params": {"delta": st.slider("Brightness change", -40, 40, 2)}}
        elif name == "contrast":
            step = {"name": "contrast", "params": {"factor": st.slider("Contrast factor", 0.7, 1.3, 1.05, 0.01)}}
        elif name == "jpeg":
            step = {"name": "jpeg", "params": {"quality": st.slider("JPEG quality", 10, 100, 90)}}
        elif name == "resize_roundtrip":
            step = {"name": "resize_roundtrip", "params": {"size": st.slider("Shrink to (px)", 32, 255, 128)}}

        b1, b2, b3, b4 = st.columns(4)
        if b1.button("Apply", type="primary", width="stretch", disabled=game_on):
            try:
                core.apply_step(edited, step)  # validate before it enters the history
                ss.history = ss.history + [step]
                ss.verify = ss.aer = ss.game = None
                st.rerun()
            except ValueError as exc:
                st.warning(f"That edit doesn't fit: {exc}")
        if b2.button("Surprise me", width="stretch", help="A random invisible edit at a hidden spot: then "
                     "play spot-the-edit in 3 · Verify."):
            s = core.surprise(seed, ss.surprises)
            ss.surprises += 1
            ss.history = [s]
            ss.game = {"truth": (s["params"]["y"], s["params"]["x"]), "guess": None, "revealed": False}
            ss.verify = ss.aer = None
            st.rerun()
        if b3.button("Undo", width="stretch", disabled=not ss.history or game_on):
            ss.history = ss.history[:-1]
            ss.verify = ss.aer = ss.game = None
            st.rerun()
        if b4.button("Reset", width="stretch", disabled=not ss.history):
            reset_edits()
            st.rerun()

        st.markdown("**Edit history**")
        if game_on:
            st.info("Hidden: a spot-the-edit game is running. Find the edit in **3 · Verify**.")
        elif not ss.history:
            st.caption("No edits yet.")
        else:
            for i, s in enumerate(ss.history, 1):
                st.markdown(f"{i}. {core.describe(s)}")

    st.markdown("### Original and edited, side by side")
    c1, c2 = st.columns(2, gap="large")
    c1.image(core.upscale(base, 768), caption="Original", output_format="PNG", width="stretch")
    c2.image(core.upscale(edited, 768), caption="Edited" if ss.history else "Edited (no edits yet)", output_format="PNG", width="stretch")
    c2.download_button("Download the edited PNG", core.to_png(edited), file_name="swapprint_edited.png", mime="image/png",
                       disabled=not ss.history)


def _rgb(hex_colour: str) -> list[int]:
    h = hex_colour.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


# ---------------------------------------------------------------- 3 · Verify


def run_verify():
    fa, fb = fp_of(base, mode), fp_of(edited, mode)
    t0 = time.perf_counter()
    cmp = sp.compare(fa, fb, shots=shots, backend="exact", seed=seed)
    ss.verify = {"key": (base_sha, edited_sha, mode, shots, seed), "cmp": cmp, "seconds": time.perf_counter() - t0,
                 "when": datetime.now(IST)}
    ss.aer = None
    ss.aer_pick = None
    if ss.game:
        ss.game = {**ss.game, "revealed": True}


@safe
def tab_verify():
    key = (base_sha, edited_sha, mode, shots, seed)
    if game_on:
        st.markdown("### Spot the edit")
        st.markdown("One pixel of this image changed by a single colour level. **Click where you think the edit is**, "
                    "then press Verify and let the SWAP test answer.")
        g1, g2 = st.columns([1, 1], gap="large")
        with g1:
            click = streamlit_image_coordinates(core.upscale(edited, 768), key="game-click", width="stretch")
            if new_click("game", click):
                ss.game = {**ss.game, "guess": click_to_canon(click)}
        with g2:
            if ss.game["guess"]:
                gy, gx = ss.game["guess"]
                st.success(f"Your guess: row {gy}, column {gx}. Now press Verify.")
            else:
                st.caption("No guess yet. You can also press Verify straight away.")
            if st.button("Verify", type="primary", key="verify-game", width="stretch"):
                run_verify()
                st.rerun()
        return

    top = st.columns([1, 3])
    if top[0].button("Verify", type="primary", width="stretch"):
        run_verify()
        st.rerun()
    v = ss.verify
    if v is None:
        top[1].markdown("Compare the edited image with the original, tile by tile, with SWAP tests. "
                        + ("" if ss.history else "_No edits yet: Verify the untouched image, or make an edit in 2 · Tamper._"))
        return
    if v["key"] != key:
        top[1].warning("The image or settings changed since the last check: press Verify again.")
        return
    cmp = v["cmp"]
    hit = cmp.tampered
    word = core.UNIT_WORD[mode]
    top[1].markdown(f'<div class="verdict {"hit" if hit else "miss"}">{core.verdict(cmp)}</div>'
                    f'<div class="lead">{core.summary_line(cmp)}</div>'
                    f'<div class="fine">{cmp.shots:,} shots per {word} · {cmp.flagged.size:,} {word}s · compared on '
                    f'the canonical 256×256 image · exact backend · {v["seconds"] * 1000:.0f} ms</div>',
                    unsafe_allow_html=True)

    g = ss.game
    if g and g["revealed"]:
        ty, tx = g["truth"]
        first = cmp.first_detection.get(core.most_suspicious(cmp))
        if cmp.tampered and cmp.mode != "perceptual" and first:
            found = f"The SWAP test found it: first 1 on shot {first} of {cmp.shots}."
        elif cmp.tampered:
            found = "The SWAP test flagged a change."
        elif cmp.mode == "strict":
            found = f"The SWAP test missed it in {cmp.shots} shots: try more shots or another seed."
        else:
            found = (f"{core.MODE_LABEL[cmp.mode]} mode did not flag it"
                     + (", by design: it ignores tiny edits." if cmp.mode == "perceptual" else
                        ": one-level edits barely move FRQI states. Switch to strict."))
        if g["guess"]:
            gy, gx = g["guess"]
            dist = float(np.hypot(gy - ty, gx - tx))
            verdict_txt = "**Hit!**" if dist <= core.GAME_HIT_PX else "**Missed.**"
            st.info(f"{verdict_txt} The edit was at row {ty}, column {tx} (white square); your guess (yellow cross) "
                    f"was {dist:.0f} px away. {found}")
        else:
            st.info(f"The edit was at row {ty}, column {tx} (white square). {found}")

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("**Where it changed**: flagged " + word + "s in magenta, stronger for larger p1. Click a " + word
                    + " to inspect it below.")
        truth = g["truth"] if g and g["revealed"] else None
        guess = g["guess"] if g and g["revealed"] else None
        click = streamlit_image_coordinates(core.heatmap(edited, cmp, 768, guess=guess, truth=truth), key="heat-click", width="stretch")
        if new_click("heat", click):
            yy, xx = click_to_canon(click)
            fp = fp_of(base, mode)
            ss.aer_pick = (yy // fp.unit_px) * cmp.grid[1] + xx // fp.unit_px
            ss.aer = None
    with right:
        unit = ss.aer_pick if ss.aer_pick is not None else core.most_suspicious(cmp)
        r, c = core.unit_rc(cmp, unit)
        fp = fp_of(base, mode)
        why = "picked by you" if ss.aer_pick is not None else "most suspicious by the exact overlap"
        st.markdown(f"**{word.title()} (row {r}, col {c})**, {why}: overlap {cmp.overlap.flat[unit]:.4f}, "
                    f"p1 {cmp.p1.flat[unit]:.4f}, {int(cmp.ones.flat[unit])} ones in {cmp.shots:,} shots")
        za, zb = core.zoom_pair(base, edited, unit, cmp.grid, fp.unit_px, 230)
        z1, z2 = st.columns(2)
        z1.image(za, caption="original", output_format="PNG", width="stretch")
        z2.image(zb, caption="edited", output_format="PNG", width="stretch")
        st.caption(core.confidence_text(cmp))
        cert = make_certificate(base, edited, cmp, artwork_title=source_note,
                                when=v["when"], heatmap_img=core.heatmap(edited, cmp, 512))
        st.download_button("Download a verification record (PNG)", cert, file_name=f"swapprint_record_{mode}.png",
                           mime="image/png", help="A shareable card with the verdict, mode, shots, miss bound, date and "
                           "thumbnails. An integrity record, not a signature.")

    live_swap_test(cmp)
    aer_panel(cmp)
    compare_encodings()


@st.fragment
def live_swap_test(cmp):
    st.markdown("### Live SWAP test")
    traced = [u for u in cmp.traces if cmp.p1.flat[u] > 0]
    if not traced:
        if cmp.mode == "perceptual":
            msg = ("Every region's fingerprint state is identical to the original's (same 64-bit hash), so p1 = 0 and "
                   "every shot reads 0. Perceptual mode may ignore pixel-level edits by design.")
        else:
            msg = (f"No {core.UNIT_WORD[cmp.mode]}'s fingerprint state differs: every SWAP test has p1 = 0 exactly, "
                   f"so every shot reads 0. That is what an untouched image looks like.")
        st.markdown(f'<div class="box">{msg}</div>', unsafe_allow_html=True)
        return
    u = traced[0]
    trace = cmp.traces[u]
    r, c = core.unit_rc(cmp, u)
    first = cmp.first_detection.get(u)
    st.markdown(f"Shots of the most suspicious {core.UNIT_WORD[cmp.mode]} (row {r}, col {c}), one by one. "
                f"Grey = 0, magenta = 1. The first 1 is outlined.")
    b1, b2, _ = st.columns([1, 1, 4])
    play = b1.button("▶ Play shots", key="play")
    show_all = b2.button("Show all", key="showall")
    box = st.empty()
    limit = 100 if cmp.mode == "perceptual" else len(trace)

    def draw(n):
        shown = trace[:min(n, limit)]
        cells = "".join(
            f'<div class="shot{" one" if v else ""}{" first" if first == i + 1 else ""}">{v}</div>'
            for i, v in enumerate(shown))
        k, m = sum(trace[:n]), n
        f, lo, hi = core.f_interval(k, m)
        more = f"<div class='fine'>…and {n - limit:,} more shots not drawn</div>" if n > limit else ""
        box.markdown(
            f'<div class="shots">{cells}</div>{more}'
            f'<div>After <b>{m:,}</b> shots: <b>{k:,}</b> ones · p̂1 = {k / m:.3f} · estimated overlap² = '
            f'<b>{f:.3f}</b> (95% Wilson interval {lo:.3f} – {hi:.3f}) · exact overlap² = {cmp.overlap.flat[u] ** 2:.4f}'
            + (f' · <b>first 1 on shot {first}</b>' if first and first <= m else "") + '</div>',
            unsafe_allow_html=True)

    if play:
        for n in range(1, min(len(trace), limit) + 1):
            draw(n)
            time.sleep(0.1)
        if len(trace) > limit:
            time.sleep(0.4)
            draw(len(trace))
    else:
        draw(len(trace) if show_all or not play else 0)


@st.fragment
def aer_panel(cmp):
    st.markdown("### Run it on a real Qiskit circuit (Aer)")
    if not AER_ENABLED:
        st.info("The Aer simulator is switched off on this deployment (memory). It runs in the local demo.")
        return
    unit = ss.aer_pick if ss.aer_pick is not None else core.most_suspicious(cmp)
    why = "picked by you on the heatmap" if ss.aer_pick is not None else "most suspicious by the exact overlap"
    r, c = core.unit_rc(cmp, unit)
    q = fp_of(base, mode).q
    a1, a2, a3 = st.columns([1, 1, 1])
    kind = a1.radio("SWAP test", ["ancilla", "destructive"], horizontal=True, key="aer-kind",
                    help="ancilla: H, controlled-SWAPs, H, measure one qubit · destructive: Bell-basis measurement, no ancilla")
    st.markdown(f"Build the actual SWAP-test circuit for **{core.UNIT_WORD[mode]} (row {r}, col {c})** ({why}), "
                f"{2 * q + (kind == 'ancilla')} qubits, and run it on Qiskit Aer's ideal simulator. This is a hybrid "
                f"demonstration: the {core.UNIT_WORD[mode]} was chosen classically.")
    aer_shots = a2.select_slider("Aer shots", [32, 128, 256, 512, 1024, 2048, 4096], 1024, key="aer-shots")
    if a3.button("Run on Qiskit Aer", type="primary", width="stretch"):
        with st.spinner("Building and simulating the circuit on Qiskit Aer (a few seconds)…"):
            try:
                res = core.run_aer(fingerprint_npz(base_sha, mode, fp_of(base, mode)),
                                   fingerprint_npz(edited_sha, mode, fp_of(edited, mode)),
                                   unit, aer_shots, kind, seed)
                ss.aer = {"unit": unit, "kind": kind, "res": res, "why": why}
            except RuntimeError as exc:
                st.warning(f"The circuit run didn't finish: {exc}. The exact result above is unaffected.")
    a = ss.aer
    if a and a["unit"] == unit:
        res = a["res"]
        lo, hi = core.wilson(res["ones"], res["shots"])
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Aer estimate of p1", f"{res['p1_est']:.3f}", help=f"{res['ones']} ones in {res['shots']} shots")
        m2.metric("Exact prediction", f"{res['p1_exact']:.3f}")
        m3.metric("Qubits", res["qubits"])
        m4.metric("Aer time", f"{res['seconds']:.2f} s")
        inside = lo <= res["p1_exact"] <= hi
        st.markdown(f"{res['ones']:,} ones in {res['shots']:,} shots ({a['kind']} SWAP test). 95% Wilson interval "
                    f"{lo:.3f} – {hi:.3f}, which {'contains' if inside else 'does not contain'} the exact p1.")
        st.caption(f"Hardware-compiled cost of a {mode} {a['kind']} SWAP test (representative unit): "
                   f"{res['two_qubit_gates']:,} two-qubit gates, depth "
                   f"{res['depth']:,} (transpiled to cx/rz/sx/x, all-to-all, optimisation level 3). That is not what Aer "
                   f"executed, and far too deep for today's devices; see Results for the noise study on small versions.")
    with st.expander("The same circuit at 2 qubits"):
        show_toy_circuit(kind)


@safe
def compare_encodings():
    st.markdown("### Compare encodings: same edit, same SWAP test, three encodings")
    if not ss.history:
        st.caption("Make an edit to compare the encodings.")
        return
    fps_a = {m: fp_of(base, m) for m in core.MODES}
    fps_b = {m: fp_of(edited, m) for m in core.MODES}
    rows = core.encoding_rows(fps_a, fps_b, seed)
    table = []
    for row in rows:
        changed = int((fps_a[row["mode"]].data != fps_b[row["mode"]].data).any(axis=1).sum())
        table.append({
            "Encoding": core.MODE_LABEL[row["mode"]],
            "Units changed / total": f"{changed:,} / {row['units']:,}",
            "Min overlap": f"{row['min_overlap']:.7f}",
            "Max p1 (exact)": f"{row['max_p1']:.3g}",
            "Shots to first 1 (most-changed unit)": core.fmt_shots(row["expected_first"], row["never"]),
            "Shots for 99% detection (that unit)": core.fmt_shots(row["shots_99"], row["never"] or "threshold rule"),
            f"Detected (default shots)": f"{'yes' if row['detected'] else 'no'} at {row['shots']:,}",
        })
    st.dataframe(table, hide_index=True, width="stretch")
    fig = go.Figure()
    xs = [core.MODE_LABEL[r["mode"]] for r in rows]
    ys = [r["expected_first"] if r["expected_first"] else None for r in rows]
    fig.add_bar(x=xs, y=ys, marker_color=[ACCENT_HEX if r["mode"] == "strict" else "#7A808C" for r in rows],
                text=[core.fmt_shots(r["expected_first"], r["never"]) for r in rows], textposition="outside")
    fig.update_layout(yaxis_type="log", yaxis_title="expected shots to the first 1 (log scale)", height=340,
                      margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font_color="#C9CDD6", showlegend=False)
    st.plotly_chart(fig, width="stretch")
    st.caption("Exact values (1/p1 from the exact overlap), no sampling, except the last column, which is one run at the "
               "seed above. Perceptual mode ignores tiny edits by design and decides by a threshold on overlap², not by "
               "a single 1.")


@safe
def check_a_file():
    with st.expander("Check a file against a registered fingerprint (no original needed)"):
        st.markdown("Upload an image and a `.npz` fingerprint from **1 · Fingerprint → Register**. The verifier never "
                    "sees the original artwork: that is the point of a fingerprint.")
        c1, c2 = st.columns(2)
        img_file = c1.file_uploader("Image to check", type=["png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"], key="chk-img")
        npz_file = c2.file_uploader("Registered fingerprint (.npz)", type=["npz"], key="chk-npz")
        st.download_button("Need a test file? Download the current edited image", core.to_png(edited),
                           file_name="swapprint_edited.png", mime="image/png", key="chk-dl")
        if not (img_file and npz_file):
            return
        try:
            ref = sp.load_fingerprint(io.BytesIO(npz_file.getvalue()))
        except Exception:  # noqa: BLE001
            st.warning("That .npz isn't a SwapPrint fingerprint.")
            return
        try:
            img, notes = core.load_upload(img_file.getvalue())
        except ValueError as exc:
            st.warning(str(exc))
            return
        problem = core.fingerprint_problem(ref)
        if problem:
            st.warning(f"That .npz isn't a usable SwapPrint fingerprint: {problem}.")
            return
        cand = sp.fingerprint(img, ref.mode)
        if ref.version != cand.version:
            st.warning(f"That fingerprint was made with a different SwapPrint version ({ref.version}).")
            return
        cmp = sp.compare(ref, cand, seed=seed)
        st.markdown(f'<div class="verdict {"hit" if cmp.tampered else "miss"}">{core.verdict(cmp)}</div>'
                    f'<div class="lead">{core.summary_line(cmp)}</div>'
                    f'<div class="fine">{core.MODE_LABEL[ref.mode]} · {cmp.shots:,} shots per unit · compared on the '
                    f'canonical 256×256 image{" · " + "; ".join(notes) if notes else ""}</div>', unsafe_allow_html=True)
        st.image(core.heatmap(img, cmp, 420), output_format="PNG", width="stretch")


# ---------------------------------------------------------------- How it works


@safe
def tab_how():
    info = sp.code_info()
    st.markdown("### Five steps from artwork to verdict")
    s = st.columns(5)
    s[0].markdown("**1 · Canonical image**\n\nResize to 256×256 RGB, deterministically on every machine.")
    s[1].markdown(f"**2 · Tiles**\n\nCut into {sp.config.STRICT_GRID**2:,} tiles of 4×4 pixels: {info['n']} bits each.")
    s[2].markdown(f"**3 · Error-correcting code**\n\nA public linear code stretches {info['n']} bits to "
                  f"{info['m']:,}. Any change spreads over about half the codeword.")
    s[3].markdown(f"**4 · Sign state**\n\nCodeword bits become the signs of an {sp.config.STRICT_Q}-qubit state's "
                  f"{info['m']:,} amplitudes.")
    s[4].markdown("**5 · SWAP test → decision**\n\nCompare with the original's state. One 1 proves the tile changed.")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("**The sign state** of a bit string c of length m = 2^q:")
        st.latex(r"|h_c\rangle = \frac{1}{\sqrt{m}} \sum_{i=0}^{m-1} (-1)^{c_i} |i\rangle, \qquad "
                 r"\langle h_a | h_b \rangle = 1 - \frac{2\,d(a,b)}{m}")
        st.markdown("**The SWAP test** reads 1 with probability")
        st.latex(r"p_1 = \frac{1 - |\langle h_a | h_b \rangle|^2}{2}")
        st.latex(r"P(\text{caught in } k \text{ shots}) = 1 - (1 - p_1)^k")
        st.markdown(f"Identical states give p1 = 0, so they **never** read 1. The code keeps any two different tiles at "
                    f"distance ≥ {info['d_min_guaranteed']} (heuristic bound), so overlap ≤ {info['overlap_max']:.3f} "
                    f"and p1 ≥ {info['p1_min']:.3f}: {sp.shots_needed(1e-3, info['p1_min'])} shots miss a changed tile "
                    f"with probability ≤ 10⁻³, {sp.shots_needed(1e-6, info['p1_min'])} shots ≤ 10⁻⁶.")
    with c2:
        st.markdown("**The SWAP-test circuit**, at 2 qubits per state (ours uses 11):")
        show_toy_circuit("ancilla")

    st.markdown("### Why the encoding matters")
    fs = frqi_vs_strict()
    st.markdown(
        f"Change one colour value of one pixel by 1 on the synthetic painting:\n\n"
        f"- **FRQI, “pixels as angles”**: overlap {fs['frqi']['overlap']:.7f}, p1 = {fs['frqi']['p1']:.2e}. The first 1 "
        f"comes after about **{fs['frqi']['first']:,.0f} shots** on average, and 99% detection needs "
        f"**{fs['frqi']['need99']:,} shots**.\n"
        f"- **SwapPrint strict**: overlap {fs['strict']['overlap']:.4f}, p1 = {fs['strict']['p1']:.3f}. The first 1 comes "
        f"after about **{fs['strict']['first']:.1f} shots**; 99% detection needs **{fs['strict']['need99']} shots**.\n\n"
        f"Same SWAP test, different encoding. The error-correcting code (Buhrman, Cleve, Watrous and de Wolf, 2001) is "
        f"what makes a tiny edit visible.")

    st.markdown("### Why quantum at all, honestly")
    st.markdown("Buhrman et al. proved that in the simultaneous-message model without shared randomness, comparing n-bit "
                "inputs needs only O(log n) qubits but Θ(√n) classical bits. That advantage holds only in that "
                "communication model. **Our simulation has no advantage; in practice SHA-256 is better.** SwapPrint is an "
                "exploration of encoding, measurement and tamper experiments.")
    st.markdown(
        '<div class="box"><b>What we don\'t claim</b><ul>'
        "<li>that it's a secure signature or watermark</li>"
        "<li>that it's a quantum advantage in our setting</li>"
        "<li>that it was run on hardware when it wasn't</li>"
        "<li>that entanglement gives security</li>"
        "<li>any number without saying how many runs it came from</li></ul>"
        "“No change detected” is not proof that nothing changed: the miss bound is P(no detection | a tile changed), "
        "not P(unchanged | no detection). A fingerprint is not secret: a strict one decodes back to the image.</div>",
        unsafe_allow_html=True)


# ---------------------------------------------------------------- Results


@safe
def tab_results():
    st.markdown("### Results")
    st.caption("Figures from experiments/figures/, exactly as listed in captions.json (tamper experiments) and "
               "core_captions.json (circuits, noise, hardware).")
    def captions(name: str) -> dict:
        try:
            return json.loads((core.FIG_DIR / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    core_caps = captions("core_captions.json")
    # each figure once; Darshan's core_* figures keep the caption from his own core_captions.json
    sections = [("Tamper experiments", {k: v for k, v in captions("captions.json").items() if k not in core_caps}),
                ("Circuits and noise", core_caps)]
    shown = 0
    for heading, caps in sections:
        figs = [(png, cap) for png, cap in caps.items() if (core.FIG_DIR / png).exists()]
        if not figs:
            continue
        st.markdown(f"#### {heading}")
        for png, caption in figs:
            st.image(str(core.FIG_DIR / png), output_format="PNG", width="stretch")
            st.caption(caption)
            st.divider()
            shown += 1
    if not (core.FIG_DIR / "captions.json").exists():
        st.info("The tamper-experiment figures (F1–F5) and the classical baseline table arrive with milestone E2.")
    if shown == 0:
        st.info("No figures yet.")


with tabs[0]:
    tab_fingerprint()
with tabs[1]:
    tab_tamper()
with tabs[2]:
    tab_verify()
    check_a_file()
with tabs[3]:
    tab_how()
with tabs[4]:
    tab_results()
