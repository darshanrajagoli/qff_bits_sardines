"""SwapPrint: quantum fingerprints for digital art, checked with a SWAP test.

    streamlit run app/streamlit_app.py --server.headless true
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # Streamlit runs scripts off the main thread; the macOS GUI backend crashes there

import html  # noqa: E402
import io  # noqa: E402
import logging  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402
from streamlit_image_coordinates import streamlit_image_coordinates  # noqa: E402

import importlib  # noqa: E402

import certificate  # noqa: E402
import core  # noqa: E402

# Streamlit re-runs only this script; a redeploy can leave the old core/certificate modules in memory (the Tamper
# crosshair failed live with an AttributeError on core.mark_point). Reload each one whose file has changed.
for _mod in (core, certificate):
    _mtime = os.path.getmtime(_mod.__file__)
    if getattr(_mod, "_sp_mtime", None) != _mtime:
        importlib.reload(_mod)
        _mod._sp_mtime = _mtime
from certificate import make_certificate  # noqa: E402
import swapprint as sp  # noqa: E402

st.set_page_config(page_title="SwapPrint", page_icon=":material/fingerprint:", layout="wide")

AER_ENABLED = os.environ.get("SWAPPRINT_NO_AER", "") != "1"
from swapprint import style  # noqa: E402

G100 = style.tokens("g100")
PURPLE, ALERT = style.PURPLE, style.ALERT  # one accent; magenta only for "change detected"
CANON = sp.config.CANON
IST = timezone(timedelta(hours=5, minutes=30), "IST")
LOG = logging.getLogger("swapprint.app")


@st.cache_resource(show_spinner=False)
def carbon_css() -> str:
    """Darshan's Carbon CSS (docs/style/carbon.css) plus the app's title gradient; empty if the file is missing."""
    try:
        css = (Path(__file__).resolve().parents[1] / "docs" / "style" / "carbon.css").read_text(encoding="utf-8")
    except OSError:
        css = ""
    g = style.WEBSITE_GRADIENT  # the event site's .text-gradient, used for the page title only
    return css + f"""
.sp-title {{display: inline-block; font-size: 3rem; font-weight: 600; line-height: 1.15; margin: 0 0 var(--sp-03, 8px) 0;
  background: linear-gradient(120deg, {g[0]} 0%, {g[1]} 42%, {g[2]} 100%); -webkit-background-clip: text;
  background-clip: text; color: transparent;}}
.sp-sub {{color: var(--text-secondary, #c6c6c6); font-size: 1.25rem; line-height: 1.4; margin-bottom: var(--sp-05, 16px);}}
.sp-credit {{color: var(--text-helper, #a8a8a8); font-size: 0.75rem; letter-spacing: 0.32px; line-height: 1.33;}}
.stButton > button:disabled, .stDownloadButton > button:disabled, [data-testid^="stBaseButton"]:disabled,
.stButton > button:disabled:hover, [data-testid^="stBaseButton"]:disabled:hover {{
  background: transparent; border: 1px solid #525252; color: #8d8d8d; cursor: not-allowed;}}
.stButton > button[kind="primary"]:disabled, [data-testid="stBaseButton-primary"]:disabled,
[data-testid="stBaseButton-primary"]:disabled:hover {{background: #525252; border-color: transparent; color: #8d8d8d;}}
.sp-steps {{display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: var(--sp-04, 12px);
  margin: var(--sp-03, 8px) 0 var(--sp-07, 32px) 0;}}
.sp-step {{background: var(--layer-01, #262626); border-top: 4px solid {PURPLE}; padding: var(--sp-05, 16px);
  display: flex; flex-direction: column; gap: var(--sp-03, 8px); transition: background 110ms;}}
.sp-step:hover {{background: var(--layer-hover-01, #333333);}}
.sp-step .num {{font: 600 2rem/1 var(--font-mono, "IBM Plex Mono"), monospace; color: #a56eff;}}
.sp-step .viz {{height: 120px; display: flex; align-items: center; justify-content: center; background: #161616;}}
.sp-step .viz img {{max-width: 100%; max-height: 120px; image-rendering: pixelated;}}
.sp-step .ttl {{font-weight: 600; font-size: 1rem; line-height: 1.375; color: var(--text-primary, #f4f4f4);}}
.sp-step .txt {{font-size: 0.875rem; line-height: 1.43; color: var(--text-secondary, #c6c6c6);}}
.sp-step .viz .shots {{flex-direction: column; gap: 2px; margin: 0;}}
@media (max-width: 1279px) {{.sp-steps {{grid-template-columns: repeat(3, minmax(0, 1fr));}}}}
@media (max-width: 640px) {{.sp-steps {{grid-template-columns: 1fr;}}}}
.sp-step .viz .shots div {{display: flex; gap: 3px; align-items: center;}}
.sp-step .viz .shots .lab {{font-size: 0.75rem; color: var(--text-helper, #a8a8a8); margin-top: 4px;}}
.sp-step .viz .shot {{width: 13px; height: 13px; font-size: 9px; flex: none;}}
.sp-vs {{display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: var(--sp-05, 16px); margin: var(--sp-03, 8px) 0;}}
.sp-stat {{background: var(--layer-01, #262626); padding: var(--sp-06, 24px); border-left: 4px solid var(--cds-gray-60, #6f6f6f);}}
.sp-stat.win {{border-left-color: {PURPLE};}}
.sp-stat .big {{font: 600 3rem/1.1 var(--font-mono, "IBM Plex Mono"), monospace; color: var(--text-primary, #f4f4f4); margin: var(--sp-03, 8px) 0;}}
.sp-stat.win .big {{color: #a56eff;}}
.sp-stat .lbl {{font-size: 0.875rem; font-weight: 600; letter-spacing: 0.16px; color: var(--text-secondary, #c6c6c6);}}
.sp-stat .det {{font-size: 0.875rem; line-height: 1.43; color: var(--text-helper, #a8a8a8); margin-top: var(--sp-03, 8px);}}
"""


def _one_line(css: str) -> str:
    """Comments and blank lines end a <style> block in Streamlit's markdown, so inject the CSS as one line."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return re.sub(r"\s+", " ", css).strip()


# Colour tokens per mode (Carbon white / g100), read by app/pixel.css. Viewers switch mode in ⋮ → Settings.
TOKENS = {
    "dark": {"background": "#161616", "layer-01": "#262626", "layer-02": "#393939", "layer-hover-01": "#333333",
             "text-primary": "#f4f4f4", "text-secondary": "#c6c6c6", "text-helper": "#a8a8a8",
             "border-subtle": "#525252", "border-strong": "#8d8d8d", "accent": "#8a3ffc", "accent-hover": "#6929c4",
             "accent-text": "#be95ff", "accent-shadow": "#31135e", "alert": "#ee5396", "alert-text": "#ff7eb6",
             "link": "#be95ff", "focus": "#ffffff", "grid-dot": "rgba(244,244,244,0.07)", "viz-bg": "#161616",
             "disabled-bg": "#393939", "disabled-text": "#8d8d8d", "support-info": "#4589ff",
             "support-warning": "#f1c21b", "support-success": "#42be65", "support-error": "#fa4d56"},
    "light": {"background": "#ffffff", "layer-01": "#f4f4f4", "layer-02": "#e0e0e0", "layer-hover-01": "#e8e8e8",
              "text-primary": "#161616", "text-secondary": "#525252", "text-helper": "#6f6f6f",
              "border-subtle": "#c6c6c6", "border-strong": "#8d8d8d", "accent": "#8a3ffc", "accent-hover": "#6929c4",
              "accent-text": "#6929c4", "accent-shadow": "#31135e", "alert": "#ee5396", "alert-text": "#d02670",
              "link": "#6929c4", "focus": "#8a3ffc", "grid-dot": "rgba(22,22,22,0.08)", "viz-bg": "#161616",
              "disabled-bg": "#e0e0e0", "disabled-text": "#8d8d8d", "support-info": "#0043ce",
              "support-warning": "#b28600", "support-success": "#24a148", "support-error": "#da1e28"},
}


def _tokens(mode: str) -> str:
    return "".join(f"--{k}: {v};" for k, v in TOKENS[mode].items())


# Not cached: a Streamlit Cloud redeploy can keep the server process, and a cached copy then hides edits to
# this file. It's a few KB, so reading it on each run costs nothing.
def figure_notes() -> dict:
    """Plain-language titles and summaries for the Results figures (app/figure_notes.json); {} if missing."""
    try:
        return json.loads((Path(__file__).resolve().parent / "figure_notes.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


# Not cached: a Streamlit Cloud redeploy can keep the server process, and a cached copy then hides edits to
# this file. It's a few KB, so reading it on each run costs nothing.
def pixel_css() -> str:
    """Both token sets, then app/pixel.css (which only reads the tokens). app/page.js marks
    <html data-sp-mode="light|dark"> from the page's real background; before it runs, the system preference decides."""
    try:
        css = (Path(__file__).resolve().parent / "pixel.css").read_text(encoding="utf-8")
    except OSError:
        css = ""
    return (f":root {{{_tokens('dark')}}}"
            f"@media (prefers-color-scheme: light) {{ :root:not([data-sp-mode=\"dark\"]) {{{_tokens('light')}}} }}"
            f":root[data-sp-mode=\"light\"] {{{_tokens('light')}}}" + css)


# Not cached: a Streamlit Cloud redeploy can keep the server process, and a cached copy then hides edits to
# this file. It's a few KB, so reading it on each run costs nothing.
def page_js_component() -> str:
    """app/page.js, injected once into the app page itself (not the component frame), so it survives reruns."""
    try:
        code = (Path(__file__).resolve().parent / "page.js").read_text(encoding="utf-8")
    except OSError:
        return ""
    payload = json.dumps(code).replace("</", "<\\/")
    return ("<script>const d = window.parent.document;"
            "if (!d.getElementById('sp-page-js')) { const s = d.createElement('script'); s.id = 'sp-page-js';"
            f"s.textContent = {payload}; d.head.appendChild(s); }}</script>")


st.markdown(f"<style>{_one_line(carbon_css())}</style>", unsafe_allow_html=True)
st.markdown(f"<style>{_one_line(pixel_css())}</style>", unsafe_allow_html=True)
components.html(page_js_component(), height=0)


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


def notice(html: str, kind: str = "info") -> None:
    """A Carbon inline notification (carbon.css .cds-notice): layer background, coloured bar on the left."""
    st.markdown(f'<div class="cds-notice {kind}">{html}</div>', unsafe_allow_html=True)


def say(text: str, kind: str = "") -> None:
    """One short game-style line (pixel.css .sp-line), shown as '* text'. It only restates what the data shows."""
    st.markdown(f'<div class="sp-line {kind}">* {text}</div>', unsafe_allow_html=True)


def safe(fn):
    """Run a UI section; show a friendly message instead of a traceback."""
    def wrapped(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as exc:  # noqa: BLE001
            LOG.exception("UI section %s failed", fn.__name__)  # full traceback in the server log, never on screen
            st.error(f"Something went wrong here ({type(exc).__name__}). Try Reset, or another artwork.")
            if os.environ.get("SWAPPRINT_DEBUG"):
                st.exception(exc)
    return wrapped


# ---------------------------------------------------------------- state

ss = st.session_state
ss.setdefault("history", [])
ss.setdefault("surprises", 0)
ss.setdefault("game", None)  # {"kind": "surprise" | "challenge", "guess": (y, x) | None, "revealed": bool}
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
    # the box is a one-line text input that cuts long names off, so the full name sits underneath, wrapped
    st.markdown(f'<div class="sp-artwork-full">{html.escape(labels[choice])}</div>', unsafe_allow_html=True)

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
                    help="strict: catches changes to exact pixels, with a probability you set by the shots · "
                         "perceptual: compares a coarse content summary, so small visible edits can be missed · "
                         "frqi: the textbook pixels-as-angles baseline")
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
    st.markdown('<div class="sp-modes"><a class="sp-mode light" href="#theme-light">☀ Light</a>'
                '<a class="sp-mode dark" href="#theme-dark">☾ Dark</a></div>', unsafe_allow_html=True)
    st.caption("Double-click an artwork preview for full screen.")
    st.markdown('<div class="sp-credit">SwapPrint · team sardines: Ansh Varma (aviate15), Darshan Rajagoli '
                '(darshanrajagoli) and Rashida Baldiwala (rsb17) on GitHub.<br><br>'
                'Type: Departure Mono by Helena Zhang (headings) and '
                'IBM Plex Mono (text), both SIL OFL 1.1. '
                'Colours: Carbon Design System tokens (Apache-2.0). Not made or endorsed by IBM.</div>',
                unsafe_allow_html=True)

edited = core.replay(base, ss.history)
edited_sha = core.sha(edited)
game = ss.game
game_on = bool(game and not game["revealed"])

st.markdown('<div class="sp-title">SwapPrint<span class="sp-cursor"></span></div><br>'
            '<div class="sp-sub">Quantum fingerprints for digital art, checked with a SWAP test</div>',
            unsafe_allow_html=True)
st.markdown('<div class="lead">In strict mode, every 4×4 patch gets an 11-qubit quantum fingerprint. A SWAP test '
            'compares fingerprints: in the ideal noiseless model an untouched patch never fires, and a typical changed '
            'patch fires about half the time.</div>',
            unsafe_allow_html=True)

# ---------------------------------------------------------------- Start here (welcome section above the tabs)


@safe
def tab_start():
    """A no-jargon guide for someone who knows nothing about quantum fingerprinting. Numbers come from code."""
    info, cfg = sp.code_info(), sp.config
    fs = frqi_vs_strict()
    lo, hi = core.single_bit_flips()
    p1 = fs["strict"]["p1"]
    miss1, miss_default = 1 - p1, (1 - p1) ** cfg.DEFAULT_SHOTS
    tiles = cfg.STRICT_GRID ** 2

    st.markdown(
        '<div class="sp-hero"><div class="kicker">START HERE · NO QUANTUM KNOWLEDGE NEEDED</div>'
        '<div class="big">Can a quantum test spot a pixel you can\'t?</div>'
        '<div class="sub">SwapPrint gives every small patch of a painting a fingerprint made for a quantum computer, '
        "then compares the original with a copy. Change one pixel by the smallest step and the test notices, and "
        "shows you where.</div>"
        '<div class="sp-badges">'
        f'<div class="sp-badge"><b>{tiles:,}</b><span>patches per image</span></div>'
        f'<div class="sp-badge"><b>{cfg.STRICT_Q} qubits</b><span>per patch fingerprint</span></div>'
        f'<div class="sp-badge"><b>{fs["strict"]["need99"]} shots</b><span>to catch a 1-pixel edit 99% of the time</span></div>'
        "</div></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="sp-vs"><div class="sp-card win"><div class="lbl">THE QUESTION</div>'
        '<div class="det">Has anyone changed this digital painting, even by one pixel you could never see? '
        "And if so, where?</div></div>"
        '<div class="sp-card win"><div class="lbl">OUR ANSWER</div>'
        '<div class="det">Fingerprint every patch as a quantum state, then compare original and copy with a small '
        "quantum circuit called the <b>SWAP test</b>. A changed patch makes it fire; a heatmap shows where.</div>"
        "</div></div>", unsafe_allow_html=True)
    st.caption("A research demo of encoding and measurement, run on a simulator of a perfect quantum computer. "
               "It is not a security product; see “What this is not” below.")

    st.markdown("#### Try it in 60 seconds")
    with st.container(border=True):
        st.markdown(
            "1. **Sidebar:** keep any artwork and the encoding **strict**.\n"
            "2. **[2 · Tamper](#go-tamper):** press **Surprise me**. It changes one colour value of one pixel by 1 (out of 255) "
            "at a hidden spot. Nobody can see that.\n"
            "3. **[3 · Verify](#go-verify):** click where you think the edit is, then press **Verify**.\n"
            f"4. **The result:** `CHANGE DETECTED`, and the heatmap marks the one changed patch out of {tiles:,}. "
            f"A changed patch makes the test fire about half the time (p1 = {p1:.2f} for this kind of edit), so the "
            f"first alarm usually comes within about {fs['strict']['first']:.0f} tries, and "
            f"{fs['strict']['need99']} tries catch it 99% of the time.\n"
            "5. Press **▶ Play shots** to watch the test run one try at a time.")

    st.markdown("#### What's going on, without the maths")
    st.markdown('<div class="sp-steps">' + "".join(
        f'<div class="sp-step"><div class="num">{n}</div><div class="ttl">{t}</div><div class="txt">{txt}</div></div>'
        for n, t, txt in [
            ("1", "Same size for everyone", f"Every image is resized to {cfg.CANON}×{cfg.CANON} pixels the same way "
             "on every computer, so the original and the copy are compared fairly."),
            ("2", "Cut into patches", f"The image is cut into {tiles:,} small patches of {cfg.STRICT_TILE}×"
             f"{cfg.STRICT_TILE} pixels. Each patch is {info['n']} bits (ones and zeros)."),
            ("3", "Spread out any change", f"Each patch goes through an error-correcting code that stretches its "
             f"{info['n']} bits to {info['m']:,}. Change even one bit and {lo:,}–{hi:,} of the {info['m']:,} bits "
             "flip. That is what makes a tiny edit easy to catch."),
            ("4", "Make it quantum", f"The {info['m']:,} bits become the + and − signs of a {cfg.STRICT_Q}-qubit "
             f"quantum state (a state of {cfg.STRICT_Q} qubits has 2^{cfg.STRICT_Q} = {info['m']:,} amplitudes, one sign each). That state is the "
             "patch's fingerprint."),
            ("5", "Compare with the SWAP test", "Each try (a “shot”) gives 0 or 1. On a perfect quantum computer an "
             "unchanged patch never gives 1; a changed patch gives 1 about half the time. One 1 flags the patch."),
        ]) + "</div>", unsafe_allow_html=True)

    # the table and the glossary fold away so the guide stays short (Codex UI/UX audit, Ansh's call)
    with st.expander("**Experiments you can run** · what to change and what you should see", icon=":material/science:"):
        st.markdown(
            "| Change this | Where | What you should see |\n|---|---|---|\n"
            f"| **Shots per tile** down to 1 | Sidebar, strict | One try catches a changed patch only about "
            f"{1 - miss1:.0%} of the time, so Verify sometimes says `NO CHANGE DETECTED`. That is why “no change "
            f"detected” is never proof. At the default {cfg.DEFAULT_SHOTS} tries the miss chance for that patch is "
            f"about {miss_default:.0e}. |\n"
            "| **Seed** | Sidebar | Same seed, same random tries and the same hidden Surprise spot. Change it to re-roll. |\n"
            f"| **Encoding: perceptual** | Sidebar | Compares a coarse summary of {cfg.PERCEPTUAL_GRID ** 2} big regions "
            f"(a {cfg.PERCEPTUAL_BITS}-bit “perceptual hash” each) instead of exact pixels. A one-pixel edit is ignored by "
            "design (`NO CONTENT CHANGE DETECTED`); a pasted patch or text is often flagged; a JPEG re-save usually "
            "is not. Small edits such as short text can be missed. |\n"
            f"| **Encoding: frqi** | Sidebar | The textbook way: pixels as angles, no code. The same one-pixel edit "
            f"then needs about {fs['frqi']['need99']:,} tries for 99% detection instead of {fs['strict']['need99']}. |\n"
            "| **Other edit tools** | [2 · Tamper](#go-tamper) | Brightness or contrast changes many pixels, so strict flags most "
            "patches; Patch, Text and Splice light up only where you edited. |\n"
            "| **Compare encodings** | [3 · Verify](#go-verify) | The same edit through all three encodings, side by side. |\n"
            "| **Run on Qiskit Aer** | [3 · Verify](#go-verify) | Builds the actual SWAP-test circuit for one patch and simulates it; "
            "its estimate should match the exact prediction within its error bar. |\n"
            "| **Register / Check a file** | [3 · Verify](#go-verify) | Save the original's fingerprint, then check a copy against "
            "it without the original image. |\n"
            "| **Challenge a friend** | [2 · Tamper](#go-tamper) | Hide your own edit and let a friend race the SWAP test. |")

    with st.expander("**Words you will see** · a glossary, from bit to SWAP test", icon=":material/menu_book:"):
        st.markdown(
            "| Term | Meaning |\n|---|---|\n"
            "| **Bit** | A 0 or a 1. Images are stored as bits. |\n"
            "| **Qubit** | The quantum version of a bit. The state of *q* qubits is described by 2^*q* numbers (amplitudes). |\n"
            "| **Quantum state** | What a group of qubits holds. Ours is a list of + and − signs, one per codeword bit. |\n"
            "| **Error-correcting code / codeword** | A fixed recipe that turns a short bit string into a long one so "
            "that any two different inputs end up very different. The long result is the codeword. |\n"
            "| **Fingerprint** | All the patches' quantum states for one image. |\n"
            "| **Tile / patch, region** | A 4×4-pixel patch (strict, frqi) or a 64×64-pixel region (perceptual): the unit "
            "that gets its own test. |\n"
            "| **SWAP test** | A small quantum circuit that compares two quantum states without reading them out. It "
            "gives 0 or 1; in the ideal noiseless model, identical states never give 1. |\n"
            "| **Shot** | One run of the test: one 0-or-1 answer. More shots, more confidence. |\n"
            "| **Overlap** | How similar two states are: 1 means identical, 0 means completely different (only its square matters for the test). |\n"
            "| **p1** | The chance that one shot gives 1: (1 − overlap²) / 2. |\n"
            "| **Encoding** | How pixels are turned into a quantum state: strict, perceptual or frqi. |\n"
            "| **Threshold** | For perceptual mode: how similar regions must stay to count as unchanged "
            f"(estimated overlap² ≥ {cfg.PERCEPTUAL_F_THRESHOLD}). |\n"
            "| **Seed** | A number that fixes the random results, so a run can be repeated exactly. |\n"
            "| **Exact backend** | The default: computes each patch's p1 exactly and draws the shots from it, matching "
            "in distribution what a perfect quantum computer would give. |\n"
            "| **Qiskit, Aer** | Qiskit is the open-source quantum programming toolkit; Aer is its simulator. |\n"
            "| **Noise, hardware** | Real quantum chips make errors. On small toy versions, identical states then "
            "give 1s too, so a real device needs a threshold (Results, F6 simulated noise and F8 a real chip). |\n"
            "| **Miss bound** | The chance of missing a patch that did change. It is not the chance the image is "
            "unchanged. |\n"
            "| **Heuristic** | A bound proven for a random code; ours is a fixed pseudo-random code, so we treat it as a "
            "well-tested rule of thumb and check it with measurements. |")

    q1, q2 = st.columns(2, gap="large")
    q1.markdown(
        '<div class="cds-notice warning" style="margin-top:0"><b>What this is not</b><ul>'
        "<li>Not a secure signature or watermark: anyone can make a fingerprint, and a strict fingerprint can be "
        "decoded back to the image.</li>"
        "<li>Not faster than ordinary computers here: a classical hash (SHA-256) does this job better in practice.</li>"
        "<li>“No change detected” is not proof that nothing changed.</li>"
        "<li>The full 11-qubit test is far too big for today's quantum chips; only small toy versions ran on a real "
        "one.</li></ul></div>", unsafe_allow_html=True)
    with q2.container(border=True):
        st.markdown(
            "**Read more**\n\n"
            "- Buhrman, Cleve, Watrous and de Wolf, *Quantum fingerprinting* (2001), the idea we build on: "
            "[arXiv:quant-ph/0102001](https://arxiv.org/abs/quant-ph/0102001)\n"
            "- Garcia-Escartin and Chamorro-Posada, *SWAP test and Hong-Ou-Mandel effect are equivalent* (2013): "
            "[arXiv:1303.6814](https://arxiv.org/abs/1303.6814)\n"
            "- [Qiskit](https://github.com/Qiskit/qiskit), the toolkit we use\n"
            "- In this app: **[How it works](#go-how)** for the maths, **[Results](#go-results)** for every experiment and figure.")


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
            f"A single-bit change flips {core.single_bit_flips()[0]}–{core.single_bit_flips()[1]} of the "
            f"{info['m']:,} signs (exact, over all {info['n']} bit positions).\n"
            f"- Heuristic guarantee: two different tiles differ in {info['d_min_guaranteed']:,} to "
            f"{info['m'] - info['d_min_guaranteed']:,} codeword bits, so |overlap| ≤ {info['overlap_max']:.3f}, every changed tile has "
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
    n_changed = int(changed.sum())
    # ring the same tiles on the original too, so the colour jump can be compared side by side (not during the game)
    ring_both = bool(ss.history) and not game_on and 0 < n_changed
    c1.image(core.mosaic_image(fa, 420, changed if ring_both else None), output_format="PNG", width="stretch",
             caption="Original's mosaic" + (" (the same tiles ringed)" if ring_both and n_changed <= 60 else ""))
    if not ss.history:
        c2.info("Make an edit in **[2 · Tamper](#go-tamper)** to see the edited image's mosaic here.")
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
                   "canonical image from it. Check a file against it in **[3 · Verify](#go-verify)**, without the original.")
    elif mode == "perceptual":
        st.caption("A perceptual fingerprint reveals only a coarse 64-bit hash per region.")
    else:
        st.caption("An FRQI fingerprint stores the pixel values as angles: it reveals the image.")


# ---------------------------------------------------------------- 2 · Tamper


@safe
def tab_tamper():
    if game_on and ss.game["kind"] == "surprise":
        say("One pixel changed by one colour level. You can't see it. Can the SWAP test?")
    elif game_on:
        say("Your edits are hidden. Hand over: your friend guesses in 3 · Verify.")
    # original and edited side by side at the top, so nobody has to scroll to find them; the edited one is clickable
    orig_col, edit_col, right = st.columns([1, 1, 1.2], gap="medium")
    with orig_col:
        st.markdown("**Original**")
        st.image(core.upscale(base, 768), output_format="PNG", width="stretch")
        st.caption("Untouched, for comparison.")
    with edit_col:
        st.markdown("**Edited**")
        # read this run's click before drawing, so the crosshair lands on it now rather than one click late
        if new_click("tamper", st.session_state.get("tamper-click")):
            ss.loc = click_to_canon(st.session_state["tamper-click"])
        pic = core.upscale(edited, 768)
        if not game_on:  # the marker would give a hidden edit away
            pic = core.mark_point(pic, *ss.loc)
        click = streamlit_image_coordinates(pic, key="tamper-click", width="stretch")
        if new_click("tamper", click):
            ss.loc = click_to_canon(click)
        y, x = ss.loc
        if game_on:
            st.caption("Location hidden while the game runs.")
        else:
            st.caption(f"Click the picture to choose where to edit. Chosen: row {y}, column {x}"
                       + ("" if ss.history else " · no edits yet"))
        st.download_button("Download the edited PNG", core.to_png(edited), file_name="swapprint_edited.png",
                           mime="image/png", disabled=not ss.history, width="stretch")
    with right.container(border=True):
        st.markdown("**Edit tools**")
        name = st.selectbox("Tool", list(core.TOOLS), format_func=lambda n: core.TOOLS[n][0], key="tool")
        st.markdown(f'<div class="sp-artwork-full">{html.escape(core.TOOLS[name][0])}</div>', unsafe_allow_html=True)
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
            s = st.text_input("Text", "FAKE", max_chars=24).strip() or "FAKE"
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

        # the tools column is narrow (it shares the row with both pictures), so the long labels get rows of their own
        b1 = st.container()
        b4, b5 = st.columns(2)
        b2, b3 = st.container(), st.container()
        if b1.button("Apply", type="primary", width="stretch", disabled=game_on):
            try:
                result = core.apply_step(edited, step)
                if np.array_equal(result, edited):
                    st.warning("That edit changes no pixels here. Move the spot or change the settings.")
                else:
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
            ss.game = {"kind": "surprise", "guess": None, "revealed": False}
            ss.verify = ss.aer = None
            st.rerun()
        if b3.button("Challenge a friend", width="stretch", disabled=np.array_equal(edited, base) or game_on,
                     help="Make an edit that changes pixels to enable a challenge. Hide your edits, then hand over: "
                          "your friend guesses in 3 · Verify, against the SWAP test."):
            ss.game = {"kind": "challenge", "guess": None, "revealed": False}
            ss.verify = ss.aer = None
            st.rerun()
        if b4.button("Undo", width="stretch", disabled=not ss.history or game_on):
            ss.history = ss.history[:-1]
            ss.verify = ss.aer = ss.game = None
            st.rerun()
        if b5.button("Reset", width="stretch", disabled=not ss.history):
            reset_edits()
            st.rerun()

        st.markdown("**Edit history**")
        if game_on:
            st.info("Hidden: a spot-the-edit game is running. Find the edit in **[3 · Verify](#go-verify)**. Reset ends the game.")
        elif not ss.history:
            st.caption("No edits yet.")
        else:
            for i, s in enumerate(ss.history, 1):
                st.markdown(f"{i}. {core.describe(s)}")


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
        if ss.game["kind"] == "challenge":
            st.markdown("Your friend edited this image somewhere. **Click where you think the edit is**, then press "
                        "Verify and see whether you or the SWAP test found it.")
        else:
            st.markdown("One pixel of this image changed by a single colour level. **Click where you think the edit "
                        "is**, then press Verify and let the SWAP test answer.")
        g1, g2 = st.columns([1, 1], gap="large")
        with g1:
            pic = core.upscale(edited, 768).convert("RGB")
            if ss.game["guess"]:
                core.draw_guess(pic, ss.game["guess"])  # the same yellow cross the reveal uses
            click = streamlit_image_coordinates(pic, key="game-click", width="stretch")
            if new_click("game", click):
                ss.game = {**ss.game, "guess": click_to_canon(click)}
                st.rerun()  # redraw at once with the cross on the guess
        with g2:
            if ss.game["guess"]:
                gy, gx = ss.game["guess"]
                say(f"Your guess: row {gy}, column {gx}. Press Verify.")
            else:
                say("Click where you think the edit is, or press Verify now.", "quiet")
            if st.button("Verify", type="primary", key="verify-game", width="stretch"):
                run_verify()
                st.rerun()
        return

    # the Verify button on its own centred row; the verdict and its summary go full width underneath
    _, mid, _ = st.columns([1, 1, 1])
    if mid.button("Verify", type="primary", width="stretch"):
        run_verify()
        st.rerun()
    v = ss.verify
    if v is None:
        st.markdown("Compare the edited image with the original, tile by tile, with SWAP tests. "
                        + ("" if ss.history else "_No edits yet: Verify the untouched image, or make an edit in [2 · Tamper](#go-tamper)._"))
        return
    if v["key"] != key:
        st.warning("The image or settings changed since the last check: press Verify again.")
        return
    cmp = v["cmp"]
    hit = cmp.tampered
    word = core.UNIT_WORD[mode]
    st.markdown(f'<div class="verdict {"hit" if hit else "miss"}">{core.verdict(cmp)}</div>'
                    f'<div class="lead">{core.summary_line(cmp)}</div>'
                    f'<div class="fine">{cmp.shots:,} {"shot" if cmp.shots == 1 else "shots"} per {word} · '
                    f'{cmp.flagged.size:,} {word}s · compared on '
                    f'the canonical 256×256 image · exact backend · {v["seconds"] * 1000:.0f} ms</div>',
                    unsafe_allow_html=True)
    g = ss.game
    if not (g and g["revealed"]):  # a revealed game already says this in its result box
        if hit and mode != "perceptual":
            first_hit = cmp.first_detection.get(core.most_suspicious(cmp))
            if first_hit:
                say(f"Found it. On the most suspicious {word}, the first 1 came on shot {first_hit}.", "hit")
        elif not hit:
            say("No alarm. That isn't proof that nothing changed.", "quiet")

    box = core.changed_box(base, edited) if g and g["revealed"] else None
    if g and g["revealed"] and box:
        first = cmp.first_detection.get(core.most_suspicious(cmp))
        if cmp.tampered and cmp.mode != "perceptual" and first:
            found = (f"The SWAP test found it: on the most suspicious {word}, "
                     f"the first 1 came on shot {first} of {cmp.shots}.")
        elif cmp.tampered:
            found = "The SWAP test flagged a change."
        elif cmp.mode == "strict":
            found = (f"The SWAP test missed it in {cmp.shots} {'shot' if cmp.shots == 1 else 'shots'}: "
                     "try more shots or another seed.")
        elif cmp.mode == "perceptual":
            found = ("Perceptual mode did not flag it, by design: it ignores one-pixel edits. Switch to strict."
                     if g["kind"] == "surprise" else
                     "Perceptual mode did not flag this edit: it compares a coarse summary, so visible edits "
                     "can be missed. Try strict.")
        else:
            found = "FRQI did not flag it: small edits barely move FRQI states. Switch to strict."
        where = core.describe_box(box)
        if g["guess"]:
            dist = core.guess_distance(base, edited, g["guess"])
            verdict_txt = "<b>Hit!</b>" if dist <= core.GAME_HIT_PX else "<b>Missed.</b>"
            notice(f"{verdict_txt} The edit was {where} (white box); your guess (yellow cross) was {dist:.0f} px "
                   f"from the nearest changed pixel. {found}", "alert" if cmp.tampered else "info")
        else:
            notice(f"The edit was {where} (white box). {found}", "alert" if cmp.tampered else "info")

    left, right = st.columns([1, 1], gap="large")
    with left:
        st.markdown("**Where it changed**: flagged " + word + "s in magenta, stronger for larger p1. Click a " + word
                    + " to inspect it below.")
        truth = box
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
        same = cmp.p1.flat[unit] == 0
        why = ("picked by you" if ss.aer_pick is not None else
               f"an example {word}: no fingerprint difference anywhere" if same else "most suspicious by the exact overlap")
        st.markdown(f"**{word.title()} (row {r}, col {c})**, {why}: overlap {cmp.overlap.flat[unit]:.7f}, "
                    f"p1 {cmp.p1.flat[unit]:.3g}, {int(cmp.ones.flat[unit])} ones in {cmp.shots:,} "
                    f"{'shot' if cmp.shots == 1 else 'shots'}")
        za, zb = core.zoom_pair(base, edited, unit, cmp.grid, fp.unit_px, 230,
                                ring=core._rgb(PURPLE) if same else core.ACCENT)
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
    st.divider()
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
    _, b1, _ = st.columns([1, 1, 1])
    play = b1.button("▶ Play shots", key="play", width="stretch")
    box = st.empty()
    limit = 64

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
            f'<div class="sp-shotsum">After <b>{m:,}</b> {"shot" if m == 1 else "shots"}: <b>{k:,}</b> ones · '
            f'p̂1 = {k / m:.3f} · estimated overlap² = '
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
        draw(len(trace))


@st.fragment
def aer_panel(cmp):
    st.markdown("### Simulate the SWAP-test circuit with Qiskit Aer")
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
    if a and a["unit"] == unit and a["kind"] == kind:
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
    st.table(table, hide_index=True, width="stretch")
    fig = go.Figure()
    xs = [core.MODE_LABEL[r["mode"]] for r in rows]
    ys = [r["expected_first"] if r["expected_first"] else None for r in rows]
    fig.add_bar(x=xs, y=ys, marker_color=[PURPLE if r["mode"] == "strict" else G100["border-strong-01"]
                                          for r in rows],
                text=[core.fmt_shots(r["expected_first"], r["never"]) for r in rows], textposition="outside")
    fig.update_layout(autosize=True, yaxis_type="log", yaxis_title="expected shots to first 1 (log)", height=340,
                      margin=dict(l=10, r=10, t=30, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      # the app's body font (Plex Sans isn't loaded, so it fell back to a serif); no fixed colour, so
                      # Streamlit's chart theme picks readable text for light and dark mode
                      font_family="IBM Plex Mono, ui-monospace, monospace", showlegend=False)
    st.plotly_chart(fig, width="stretch", config={"responsive": True})
    st.caption("Exact values (1/p1 from the exact overlap), no sampling, except the last column, which is one run at the "
               "seed above. Perceptual mode ignores tiny edits by design and decides by a threshold on overlap², not by "
               "a single 1.")


@safe
def check_a_file():
    with st.expander("Check a file against a registered fingerprint (no original needed)"):
        st.markdown("Upload an image and a `.npz` fingerprint from **1 · Fingerprint → Register**. The original image "
                    "file need not be uploaded, but a stored strict fingerprint contains enough information to "
                    "reconstruct the canonical image: integrity, not secrecy.")
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
                    f'<div class="fine">{core.MODE_LABEL[ref.mode]} · {cmp.shots:,} '
                    f'{"shot" if cmp.shots == 1 else "shots"} per unit · compared on the '
                    f'canonical 256×256 image{" · " + "; ".join(notes) if notes else ""}</div>', unsafe_allow_html=True)
        st.image(core.heatmap(img, cmp, 420), output_format="PNG", width="stretch")


# ---------------------------------------------------------------- How it works


@safe
def tab_how():
    info = sp.code_info()
    fs = frqi_vs_strict()
    lo, hi = core.single_bit_flips()
    v = {k: core.data_uri(im) for k, im in core.step_visuals(base, fp_of(base, "strict")).items()}
    # step 5's "changed" row is a real draw at the one-pixel p1 below, seeded from the sidebar seed
    draws = np.random.default_rng(seed).random(8) < fs["strict"]["p1"]
    same = "".join('<span class="shot">0</span>' for _ in draws)
    diff = "".join(f'<span class="shot{" one" if d else ""}">{int(d)}</span>' for d in draws)
    steps = [
        ("1", "Canonical image", f'<img src="{v["canon"]}" alt="canonical image">',
         "Resize to 256×256 RGB, deterministically on every machine."),
        ("2", "Tiles", f'<img src="{v["zoom"]}" alt="4x4 tiles">',
         f"Cut into {sp.config.STRICT_GRID**2:,} tiles of 4×4 pixels: {info['n']} bits each. Shown: the outlined tile."),
        ("3", "Error-correcting code", f'<img src="{v["code"]}" alt="codeword bits">',
         f"A public linear code stretches {info['n']} bits to {info['m']:,} (shown: this tile's codeword). "
         f"A single-bit change flips {lo}–{hi} of the {info['m']:,} signs."),
        ("4", "Sign state", f'<img src="{v["signs"]}" alt="amplitude signs">',
         f"Codeword bits become the signs of an {sp.config.STRICT_Q}-qubit state's {info['m']:,} amplitudes "
         f"(shown: the first 32)."),
        ("5", "SWAP test → decision",
         f'<div class="shots"><span class="lab">same tile</span><div>{same}</div>'
         f'<span class="lab">changed tile</span><div>{diff}</div></div>',
         "Identical states never give a 1 in the noiseless model, so a tile that gives a 1 is flagged."),
    ]
    st.markdown("### Five steps from artwork to verdict")
    st.caption("The pictures are live: they come from the artwork selected in the sidebar.")
    st.markdown('<div class="sp-steps">' + "".join(
        f'<div class="sp-step"><div class="num">{n}</div><div class="viz">{viz}</div>'
        f'<div class="ttl">{t}</div><div class="txt">{txt}</div></div>' for n, t, viz, txt in steps) + "</div>",
        unsafe_allow_html=True)
    st.caption(f"Step 5: the “changed” row is {len(draws)} sampled shots at the one-pixel p1 = {fs['strict']['p1']:.3f} "
               f"(seed {seed}); magenta marks a 1.")

    c1, c2 = st.columns(2, gap="large")
    with c1.container(border=True):
        st.markdown("**The sign state** of a bit string $c$ of length $m = 2^q$, and the overlap of two of them:")
        st.latex(r"|h_c\rangle = \frac{1}{\sqrt{m}} \sum_{i=0}^{m-1} (-1)^{c_i} |i\rangle")
        st.latex(r"\langle h_a | h_b \rangle = 1 - \frac{2\,d(a,b)}{m}")
        st.markdown("**The SWAP test** reads 1 with probability")
        st.latex(r"p_1 = \frac{1 - |\langle h_a | h_b \rangle|^2}{2}")
        st.latex(r"P(\text{caught in } k \text{ shots}) = 1 - (1 - p_1)^k")
        st.markdown(f"Identical states give p1 = 0, so they **never** read 1 in the noiseless model. Under the "
                    f"random-code heuristic, any two different tiles differ in between {info['d_min_guaranteed']:,} "
                    f"and {info['m'] - info['d_min_guaranteed']:,} codeword bits, so |overlap| ≤ {info['overlap_max']:.3f} "
                    f"and p1 ≥ {info['p1_min']:.3f}: {sp.shots_needed(1e-3, info['p1_min'])} shots miss a changed tile "
                    f"with probability ≤ 10⁻³, {sp.shots_needed(1e-6, info['p1_min'])} shots ≤ 10⁻⁶.")
    with c2.container(border=True):
        st.markdown("**The SWAP-test circuit**, at 2 qubits per state (ours uses 11):")
        show_toy_circuit("ancilla")

    st.markdown("### Why the encoding matters")
    st.markdown("Change one colour value of one pixel by 1 on the synthetic painting, then ask how many shots the same "
                "SWAP test needs to catch it 99% of the time:")
    st.markdown(
        '<div class="sp-vs">'
        f'<div class="sp-stat"><div class="lbl">FRQI, “pixels as angles”</div>'
        f'<div class="big">{fs["frqi"]["need99"]:,}</div><div class="lbl">shots for 99% detection</div>'
        f'<div class="det">overlap {fs["frqi"]["overlap"]:.7f}, p1 = {fs["frqi"]["p1"]:.2e}; the first 1 comes after '
        f'about {fs["frqi"]["first"]:,.0f} shots on average.</div></div>'
        f'<div class="sp-stat win"><div class="lbl">SwapPrint strict, error-correcting code</div>'
        f'<div class="big">{fs["strict"]["need99"]}</div><div class="lbl">shots for 99% detection</div>'
        f'<div class="det">overlap {fs["strict"]["overlap"]:.4f}, p1 = {fs["strict"]["p1"]:.3f}; the first 1 comes after '
        f'about {fs["strict"]["first"]:.1f} shots on average.</div></div></div>',
        unsafe_allow_html=True)
    st.caption("Exact values from the two encodings, no sampling. Same SWAP test, different encoding: the "
               "error-correcting code (Buhrman, Cleve, Watrous and de Wolf, 2001) is what makes a tiny edit visible.")

    q1, q2 = st.columns(2, gap="large")
    with q1.container(border=True):
        st.markdown("**Why quantum at all, honestly**")
        st.markdown("Buhrman et al. proved that in the simultaneous-message model without shared randomness, comparing "
                    "n-bit inputs needs only O(log n) qubits but Θ(√n) classical bits. That advantage holds only in "
                    "that communication model. **Our simulation has no advantage; in practice SHA-256 is better.** "
                    "SwapPrint is an exploration of encoding, measurement and tamper experiments.")
    q2.markdown(
        '<div class="cds-notice warning" style="margin-top:0"><b>What we don\'t claim</b><ul>'
        "<li>that it's a secure signature or watermark</li>"
        "<li>that it's a quantum advantage in our setting</li>"
        "<li>that the full-image test ran on hardware: only small toy states ran on a real IBM chip (F8)</li>"
        "<li>that entanglement gives security</li>"
        "<li>any number without saying how many runs it came from</li></ul>"
        "“No change detected” is not proof that nothing changed: the miss bound is P(no detection | a tile changed), "
        "not P(unchanged | no detection). A fingerprint is not secret: a strict one decodes back to the image.</div>",
        unsafe_allow_html=True)


# ---------------------------------------------------------------- Results


@safe
def tab_results():
    st.markdown("### Results")
    st.caption("The recorded experiments: how reliably each kind of edit is caught, how much the encoding matters, "
               "circuit cost, simulated noise, and a toy run on a real IBM chip. Sources: captions.json and "
               "core_captions.json in experiments/figures/.")
    def captions(name: str) -> dict:
        try:
            return json.loads((core.FIG_DIR / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    core_caps = captions("core_captions.json")
    simple = st.toggle("Simple explanations", value=True, key="results-simple",
                       help="On: a plain-language summary above each figure, the full caption one click away. "
                            "Off: the authors' full technical captions only.")
    notes = figure_notes() if simple else {}
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
            note = notes.get(png)
            if note:  # a plain-language title and summary first; the authors' full caption one click away
                st.markdown(f"**{note['title']}**")
                st.markdown(f'<div class="sp-plain">{note["plain"]}</div>', unsafe_allow_html=True)
            st.image(str(core.FIG_DIR / png), output_format="PNG", width="stretch")
            if note:
                with st.expander("Technical details (full caption)"):
                    st.caption(caption)
            else:
                st.caption(caption)
            st.divider()
            shown += 1
    if not (core.FIG_DIR / "captions.json").exists():
        st.info("The tamper-experiment figures (F1–F5) and the classical baseline table arrive with milestone E2.")
    if shown == 0:
        st.info("No figures yet.")


# Start here sits above the tabs, closed on arrival so the tabs are the first thing seen (Ansh); ?welcome=open starts
# it open. ?welcome=closed (used by the scripted demo recordings) keeps working, since closed is the default.
with st.expander("**Start here** · a two-minute guide, no quantum knowledge needed",
                 expanded=st.query_params.get("welcome") == "open", icon=":material/explore:"):
    tab_start()

tabs = st.tabs(["1 · Fingerprint", "2 · Tamper", "3 · Verify", "How it works", "Results"])
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
