"""SwapPrint style kit: Carbon Design System colours + IBM Plex type for figures, app and video.

    from swapprint import style
    style.use("white")          # once, before plotting (figures: "white"; video frames: "g100")

Design tokens come from the open-source Carbon Design System (Apache-2.0,
@carbon/colors 11.61.0, @carbon/themes 11.84.0, @carbon/charts 1.27.25) and the fonts are IBM Plex
(SIL OFL 1.1, see swapprint/fonts/OFL.txt). The accent PURPLE is the exact violet used by the
event website q-bits.in (``--qiskit-violet:#8a3ffc``, which is Carbon Purple 60).

This is an independent project. It uses no IBM logo or wordmark and does not imply IBM endorsement.
matplotlib is imported lazily inside ``use()``, so ``import swapprint`` stays fast.
"""
from __future__ import annotations

import dataclasses
import logging
import re
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parent / "fonts"

# ---------------------------------------------------------------- Carbon v11 palette (@carbon/colors)
CARBON = {
    "white": "#ffffff", "black": "#000000",
    "gray-10": "#f4f4f4", "gray-20": "#e0e0e0", "gray-30": "#c6c6c6", "gray-40": "#a8a8a8",
    "gray-50": "#8d8d8d", "gray-60": "#6f6f6f", "gray-70": "#525252", "gray-80": "#393939",
    "gray-90": "#262626", "gray-100": "#161616",
    "blue-10": "#edf5ff", "blue-20": "#d0e2ff", "blue-30": "#a6c8ff", "blue-40": "#78a9ff",
    "blue-50": "#4589ff", "blue-60": "#0f62fe", "blue-70": "#0043ce", "blue-80": "#002d9c",
    "blue-90": "#001d6c", "blue-100": "#001141",
    "purple-10": "#f6f2ff", "purple-20": "#e8daff", "purple-30": "#d4bbff", "purple-40": "#be95ff",
    "purple-50": "#a56eff", "purple-60": "#8a3ffc", "purple-70": "#6929c4", "purple-80": "#491d8b",
    "purple-90": "#31135e", "purple-100": "#1c0f30",
    "magenta-10": "#fff0f7", "magenta-20": "#ffd6e8", "magenta-30": "#ffafd2", "magenta-40": "#ff7eb6",
    "magenta-50": "#ee5396", "magenta-60": "#d02670", "magenta-70": "#9f1853", "magenta-80": "#740937",
    "magenta-90": "#510224", "magenta-100": "#2a0a18",
    "cyan-10": "#e5f6ff", "cyan-20": "#bae6ff", "cyan-30": "#82cfff", "cyan-40": "#33b1ff",
    "cyan-50": "#1192e8", "cyan-60": "#0072c3", "cyan-70": "#00539a", "cyan-80": "#003a6d",
    "cyan-90": "#012749", "cyan-100": "#061727",
    "teal-10": "#d9fbfb", "teal-20": "#9ef0f0", "teal-30": "#3ddbd9", "teal-40": "#08bdba",
    "teal-50": "#009d9a", "teal-60": "#007d79", "teal-70": "#005d5d", "teal-80": "#004144",
    "teal-90": "#022b30", "teal-100": "#081a1c",
    "green-10": "#defbe6", "green-20": "#a7f0ba", "green-30": "#6fdc8c", "green-40": "#42be65",
    "green-50": "#24a148", "green-60": "#198038", "green-70": "#0e6027", "green-80": "#044317",
    "green-90": "#022d0d", "green-100": "#071908",
    "red-10": "#fff1f1", "red-20": "#ffd7d9", "red-30": "#ffb3b8", "red-40": "#ff8389",
    "red-50": "#fa4d56", "red-60": "#da1e28", "red-70": "#a2191f", "red-80": "#750e13",
    "red-90": "#520408", "red-100": "#2d0709",
    "yellow-30": "#f1c21b", "yellow-40": "#d2a106", "yellow-50": "#b28600",
    "orange-60": "#ba4e00", "orange-70": "#8a3800",
}

# Theme tokens (@carbon/themes generated white.js / g100.js)
THEMES = {
    "white": {
        "background": "#ffffff", "layer-01": "#f4f4f4", "layer-02": "#ffffff", "layer-hover-01": "#e8e8e8",
        "text-primary": "#161616", "text-secondary": "#525252", "text-helper": "#6f6f6f",
        "text-on-color": "#ffffff", "border-subtle-00": "#e0e0e0", "border-subtle-01": "#c6c6c6",
        "border-strong-01": "#8d8d8d", "interactive": "#0f62fe", "focus": "#0f62fe",
        "link-primary": "#0f62fe", "highlight": "#d0e2ff", "support-error": "#da1e28",
        "support-success": "#24a148", "support-warning": "#f1c21b", "support-info": "#0043ce",
    },
    "g100": {
        "background": "#161616", "layer-01": "#262626", "layer-02": "#393939", "layer-hover-01": "#333333",
        "text-primary": "#f4f4f4", "text-secondary": "#c6c6c6", "text-helper": "#a8a8a8",
        "text-on-color": "#ffffff", "border-subtle-00": "#393939", "border-subtle-01": "#525252",
        "border-strong-01": "#6f6f6f", "interactive": "#4589ff", "focus": "#ffffff",
        "link-primary": "#78a9ff", "highlight": "#001d6c", "support-error": "#fa4d56",
        "support-success": "#42be65", "support-warning": "#f1c21b", "support-info": "#4589ff",
    },
}

# Carbon data-visualisation categorical palette, 14 colours, in Carbon's own order
# (@carbon/charts scss/_color-palette.scss, 14-colour group). Carbon's data-viz page spells out the same
# hex values; its source marks yellow 40/50 and orange 60/70 as literals, repeated here.
CATEGORICAL_LIGHT = [
    "#6929c4",  # purple 70
    "#1192e8",  # cyan 50
    "#005d5d",  # teal 70
    "#9f1853",  # magenta 70
    "#fa4d56",  # red 50
    "#520408",  # red 90
    "#198038",  # green 60
    "#002d9c",  # blue 80
    "#ee5396",  # magenta 50
    "#b28600",  # yellow 50
    "#009d9a",  # teal 50
    "#012749",  # cyan 90
    "#8a3800",  # orange 70
    "#a56eff",  # purple 50
]
CATEGORICAL_DARK = [
    "#8a3ffc",  # purple 60
    "#33b1ff",  # cyan 40
    "#007d79",  # teal 60
    "#ff7eb6",  # magenta 40
    "#fa4d56",  # red 50
    "#fff1f1",  # red 10
    "#6fdc8c",  # green 30
    "#4589ff",  # blue 50
    "#d02670",  # magenta 60
    "#d2a106",  # yellow 40
    "#08bdba",  # teal 40
    "#bae6ff",  # cyan 20
    "#ba4e00",  # orange 60
    "#d4bbff",  # purple 30
]

# ---------------------------------------------------------------- SwapPrint accents
PURPLE = "#8a3ffc"        # exact: q-bits.in `--qiskit-violet` (= Carbon Purple 60); site CSS, offset 72642
ACCENT = PURPLE           # the one accent colour (buttons, highlights, "this is SwapPrint")
ACCENT_ON_DARK = "#a56eff"   # Carbon Purple 50 (the site's `--qiskit-violet-bright`): readable on g100
ALERT = "#ee5396"         # Carbon Magenta 50: "change detected" heatmaps; CVD-safe against purple
ALERT_ON_DARK = "#ff7eb6"    # Carbon Magenta 40 (g100 variant, the site's `--qff-pink`)
WEBSITE_GRADIENT = ("#ff7eb6", "#ee5396", "#8a3ffc")   # q-bits.in `.text-gradient`: 120deg, 0% / 42% / 100%

_state = {"theme": "white", "fonts": False}


class _QuietWeightFallback(logging.Filter):
    """The DejaVu glyph fallback has no semibold; matplotlib then logs a harmless 'using 700' line."""

    def filter(self, record):
        return "Failed to find font weight" not in record.getMessage()


def tokens(theme: str | None = None) -> dict:
    """Carbon theme tokens for 'white' or 'g100' (default: the theme last passed to use())."""
    return THEMES[theme or _state["theme"]]


def categorical(theme: str | None = None) -> list[str]:
    """Carbon's categorical palette for the theme: light for 'white', dark for 'g100'."""
    return list(CATEGORICAL_DARK if (theme or _state["theme"]) == "g100" else CATEGORICAL_LIGHT)


def font_paths() -> dict:
    """{'IBMPlexSans-SemiBold': Path(...), ...}: for PIL/ffmpeg/Playwright users."""
    return {p.stem: p for p in sorted(FONT_DIR.glob("*.ttf"))}


def register_fonts() -> list[str]:
    """Register the bundled Plex TTFs with matplotlib's font manager (idempotent)."""
    from matplotlib import font_manager

    if not _state["fonts"]:
        known = {f.fname for f in font_manager.fontManager.ttflist}
        for path in sorted(FONT_DIR.glob("*.ttf")):
            if str(path) not in known:
                font_manager.fontManager.addfont(str(path))
        # The Plex TTF name tables call the Medium/SemiBold files "IBM Plex Sans Medm"/"SmBld", which hides
        # them from weight lookup. Fold them into the base family so weight="medium"/"semibold" works.
        entries = font_manager.fontManager.ttflist
        for i, entry in enumerate(entries):
            if Path(entry.fname).parent == FONT_DIR:
                family = re.sub(r" (Medm|SmBld)$", "", entry.name)
                family = "IBM Plex Sans Condensed" if family == "IBM Plex Sans Cond" else family
                entries[i] = dataclasses.replace(entry, name=family)
        font_manager.fontManager._findfont_cached.cache_clear()
        logging.getLogger("matplotlib.font_manager").addFilter(_QuietWeightFallback())
        _state["fonts"] = True
    return sorted({f.name for f in font_manager.fontManager.ttflist if f.name.startswith("IBM Plex")})


def cmap(kind: str = "purple", theme: str | None = None):
    """Carbon-based colormaps. 'purple': sequential Purple 10->100 (reversed on g100);
    'alert': sequential grey -> Magenta (change heatmaps)."""
    from matplotlib.colors import LinearSegmentedColormap

    dark = (theme or _state["theme"]) == "g100"
    if kind == "purple":
        steps = [CARBON[f"purple-{n}"] for n in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100)]
        steps = steps[::-1] if dark else steps
    elif kind == "alert":
        low = CARBON["gray-100"] if dark else CARBON["gray-10"]
        steps = [low, CARBON["magenta-70" if dark else "magenta-30"], CARBON["magenta-50"],
                 CARBON["magenta-40" if dark else "magenta-60"]]
    else:
        raise ValueError("kind must be 'purple' or 'alert'")
    return LinearSegmentedColormap.from_list(f"carbon_{kind}_{'g100' if dark else 'white'}", steps)


def use(theme: str = "white") -> None:
    """Apply the SwapPrint look to matplotlib: Plex Sans, Carbon greys, Carbon categorical colours."""
    if theme not in THEMES:
        raise ValueError(f"theme must be one of {sorted(THEMES)}, got {theme!r}")
    import matplotlib as mpl
    from cycler import cycler

    register_fonts()
    t = THEMES[theme]
    _state["theme"] = theme
    grid = t["border-subtle-00"]
    mpl.rcParams.update({
        "font.family": ["IBM Plex Sans", "DejaVu Sans"],     # DejaVu only as a glyph fallback
        "font.sans-serif": ["IBM Plex Sans", "DejaVu Sans"],
        "font.monospace": ["IBM Plex Mono", "DejaVu Sans Mono"],
        "font.size": 10,
        "mathtext.fontset": "custom",
        "mathtext.rm": "IBM Plex Sans", "mathtext.it": "IBM Plex Sans:italic",
        "mathtext.bf": "IBM Plex Sans:bold", "mathtext.default": "regular",
        "text.color": t["text-primary"],
        "figure.facecolor": t["background"], "figure.edgecolor": t["background"],
        "figure.titlesize": 14, "figure.titleweight": "semibold",
        "figure.constrained_layout.use": True,
        "axes.facecolor": t["background"], "axes.edgecolor": t["border-strong-01"],
        "axes.labelcolor": t["text-secondary"], "axes.labelsize": 10,
        "axes.titlecolor": t["text-primary"], "axes.titlesize": 12, "axes.titleweight": "semibold",
        "axes.titlelocation": "left", "axes.titlepad": 8,
        "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.axisbelow": True, "axes.prop_cycle": cycler(color=categorical(theme)),
        "grid.color": grid, "grid.linewidth": 0.7, "grid.alpha": 1.0,
        "xtick.color": t["text-secondary"], "ytick.color": t["text-secondary"],
        "xtick.labelcolor": t["text-secondary"], "ytick.labelcolor": t["text-secondary"],
        "xtick.labelsize": 9, "ytick.labelsize": 9,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8,
        "xtick.major.size": 3.5, "ytick.major.size": 3.5,
        "xtick.minor.visible": False, "ytick.minor.visible": False,
        "lines.linewidth": 1.8, "lines.markersize": 5,
        "patch.edgecolor": t["background"], "patch.linewidth": 0.6,
        "legend.frameon": False, "legend.fontsize": 9, "legend.labelcolor": t["text-secondary"],
        "legend.title_fontsize": 9,
        "savefig.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.15,
        "savefig.facecolor": t["background"], "savefig.edgecolor": t["background"],
    })
    sequential = cmap("purple", theme)
    mpl.colormaps.register(sequential, name=sequential.name, force=True)
    mpl.rcParams["image.cmap"] = sequential.name


def credit() -> str:
    """The licence credit line for README/video end cards."""
    return ("Design tokens: Carbon Design System (Apache-2.0). Typeface: IBM Plex (SIL OFL 1.1). "
            "SwapPrint is an independent project and is not made or endorsed by IBM.")
