# SwapPrint style kit

Everything a judge sees (app, figures, demo video, README images) uses one look: **Carbon Design System tokens + IBM Plex type + the purple of the event site**, branded only as **SwapPrint · team sardines**.

| Piece | File |
|---|---|
| Python tokens, matplotlib theme | `swapprint/style.py` |
| Fonts (Plex Sans/Mono/Sans Condensed × Regular, Medium, SemiBold, Bold) + OFL licence | `swapprint/fonts/` (2.3 MB) |
| Streamlit theme (verified) | `docs/style/streamlit_config.toml` |
| CSS for `st.markdown(unsafe_allow_html=True)` | `docs/style/carbon.css` |
| Video title / section / lower-third / end cards | `docs/style/title_card.html` |

## Which theme where

| Surface | Theme | Notes |
|---|---|---|
| Streamlit app | **g100** (dark) by default; white is a fallback in the config comments | accent purple buttons, magenta only for "change detected" |
| Figures (F1-F7), README images | **white** | `style.use("white")`; white backgrounds print and embed cleanly |
| Demo video | **g100**, Plex title cards | the app is dark, so cards match it |

## Colours (exact hex, with sources)

Carbon v11: `@carbon/colors` 11.61.0 (`https://unpkg.com/@carbon/colors@11.61.0/es/index.js`), themes from `@carbon/themes` 11.84.0 (`.../js/generated/themes/white.js`, `g100.js`), data-viz palette from `@carbon/charts` 1.27.25 (`.../scss/_color-palette.scss`, 14-colour group). Docs: <https://carbondesignsystem.com/elements/color/overview/>.

| Role | Hex | Carbon name |
|---|---|---|
| **PURPLE / ACCENT** (site-exact) | `#8a3ffc` | Purple 60 |
| ACCENT_ON_DARK (text/lines on g100) | `#a56eff` | Purple 50 |
| **ALERT** "change detected" | `#ee5396` (`#ff7eb6` on g100) | Magenta 50 / 40 |
| Grays 10..100 | `#f4f4f4 #e0e0e0 #c6c6c6 #a8a8a8 #8d8d8d #6f6f6f #525252 #393939 #262626 #161616` | Gray 10-100 |
| Blue 60 / 70 | `#0f62fe` / `#0043ce` | |
| Purple 30/40/50/60/70 | `#d4bbff #be95ff #a56eff #8a3ffc #6929c4` | |
| Magenta 50/60 | `#ee5396` `#d02670` | |
| Cyan 40/50 · Teal 50/60 | `#33b1ff #1192e8` · `#009d9a #007d79` | |
| Green 40/50 · Red 50/60 · Yellow 30 | `#42be65 #24a148` · `#fa4d56 #da1e28` · `#f1c21b` | |

| Token | white | g100 |
|---|---|---|
| background | `#ffffff` | `#161616` |
| layer-01 / layer-02 | `#f4f4f4` / `#ffffff` | `#262626` / `#393939` |
| text-primary / secondary | `#161616` / `#525252` | `#f4f4f4` / `#c6c6c6` |
| border-subtle-00 | `#e0e0e0` | `#393939` |
| interactive / focus | `#0f62fe` / `#0f62fe` | `#4589ff` / `#ffffff` |
| support error / success / warning | `#da1e28` / `#24a148` / `#f1c21b` | `#fa4d56` / `#42be65` / `#f1c21b` |

(SwapPrint swaps Carbon's `interactive` blue for the purple accent.)

**Categorical (Carbon order, 14):**
light `#6929c4 #1192e8 #005d5d #9f1853 #fa4d56 #520408 #198038 #002d9c #ee5396 #b28600 #009d9a #012749 #8a3800 #a56eff`;
dark `#8a3ffc #33b1ff #007d79 #ff7eb6 #fa4d56 #fff1f1 #6fdc8c #4589ff #d02670 #d2a106 #08bdba #bae6ff #ba4e00 #d4bbff`.
Use the first 3 for 3 series (purple, cyan, teal). `ALERT` vs `PURPLE` stays distinguishable under protan/deutan/tritan simulation (CIE ΔE ≥ 65).

**Where the purple comes from.** `https://q-bits.in/_next/static/immutable/chunks/0di0tsxazbgqt.css` is one minified line; the offsets are 0-based character positions in it.
`:root{... --qiskit-violet:#8a3ffc; --qiskit-violet-bright:#a56eff; --qff-pink:#ff7eb6; --qff-pink-deep:#ee5396; --qff-pink-fill:#d02670; --qff-indigo:#31135e; --qff-blue:#0f62fe ...}` at offset 72642; the `.dark{}` block repeats `#8a3ffc` at 73493 (page bg `#0a0420`). The site's only gradient is `.text-gradient`, `linear-gradient(120deg, #ff7eb6 0%, #ee5396 42%, #8a3ffc 100%)`, offset 75339; other uses are `#8a3ffc` at 5-20 % alpha (grid lines at 26799, radial glows at 26985-27992). `#8a3ffc` is **Carbon Purple 60**, `#a56eff` Purple 50, the pinks are Carbon Magenta 40/50/60. The site's body font is IBM Plex Sans, mono is IBM Plex Mono (display font Bricolage Grotesque: not used here).

## Type (Carbon productive set, px/line-height)

`label-01` 12/16 (+0.32) · `body-compact-01` 14/18 · `body-01` 14/20 (+0.16) · `body-02` 16/24 · `heading-01` 14/20 SemiBold · `heading-02` 16/22 SemiBold · `heading-03` 20/28 · `heading-04` 28/36 · `heading-05` 32/40 · `heading-06` 42/50 · `code-01` 12/16 Mono · `code-02` 14/20 Mono. Sentence case; titles left-aligned; numbers in Plex Mono when they line up in a column. Figures: title 12 SemiBold, labels 10, ticks 9, legend 9 (already set by `use()`).

## Spacing

Carbon 2x grid, 8 px unit: 2, 4, 8, 12, 16, 24, 32, 40, 48, 64, 80, 96 (`--sp-01..12` in `carbon.css`). Square corners (radius 0), 48 px buttons, 1 px `border-subtle` lines.

## Figures: one line

```python
from swapprint import style; style.use("white")   # before creating figures; matplotlib imported lazily inside
```
Gives Plex Sans, Carbon text/grid greys, Carbon categorical prop_cycle, 200 dpi, constrained layout, open spines, left-aligned titles. Also: `style.categorical()`, `style.cmap("purple"|"alert")`, `style.tokens()`, `style.ALERT`, `style.CARBON["gray-60"]`. Do not call `fig.tight_layout()` (constrained layout is on), and do not hard-code colours or `grid(alpha=...)`.

## Streamlit theme (verified on Streamlit 1.66.1, headless + Playwright)

`docs/style/streamlit_config.toml` replaces `.streamlit/config.toml`. The font method that works: `[[theme.fontFaces]]` (family, `url = "app/static/fonts/<file>.ttf"`, weight, style) + `[server] enableStaticServing = true` + the TTFs copied to `app/static/fonts/` (Streamlit serves `<script dir>/static/` at `/app/static/`). Then `font = "IBM Plex Sans"`, `codeFont = "IBM Plex Mono"`. Check: `GET /app/static/fonts/IBMPlexSans-Regular.ttf` returns 200, `document.fonts.check('600 16px "IBM Plex Sans"')` is true, body/h1/button compute to `"IBM Plex Sans"`, no failed requests. The same config sets primary `#8a3ffc`, g100 backgrounds, square corners and the Carbon chart colours (`chartCategoricalColors`, `chartSequentialColors`). Inject `carbon.css` for tags, notices and tiles. Never write `.stApp * {font-family}` (it breaks the icon font).

## Video rules (1920×1080, g100)

* Title card 4 s, section cards 2.5 s, lower third 5 s, end card 4 s. Cards come from `title_card.html`; one idea per card; max 2 lines of 5 words in titles.
* Lower thirds: bottom-left, 96 px margins, purple 8 px bar, name in SemiBold + one role line. No emoji, no animation beyond the 400 ms fade.
* Captions: Plex SemiBold 40 px, white on black 72 % (the recorder's bar), sentence case.
* The end card carries the licence line (below). The word "IBM" appears only inside "IBM Plex" and the licence credit.
* Integration (recorder `app/demo/record_demo.py`): cards are served as a static page and shown as a full-screen iframe over the live app, so Streamlit's session survives. Copy `title_card.html` to `app/static/`, then add to the recorder:

```python
from urllib.parse import urlencode, quote
CARD_JS = """(src) => { let f = document.getElementById('demo-card');
  if (!src) { if (f) f.remove(); return; }
  if (!f) { f = document.createElement('iframe'); f.id = 'demo-card';
    Object.assign(f.style, {position:'fixed', inset:'0', width:'100vw', height:'100vh', border:'0', zIndex:'2147483646', background:'transparent'});
    document.body.appendChild(f); }
  f.src = src; }"""
# in do_step(), a new action (the storyboard step may set "say": "" so no caption sits on the card):
elif act == "card":      # {"action":"card","kind":"title|section|lower|end","title":..,"sub":..,"num":..,"hold":4}
    q = urlencode({k: step[k] for k in ("kind","title","sub","kicker","num","foot","theme") if k in step}, quote_via=quote)
    page.evaluate(CARD_JS, f"{BASE_URL}/app/static/title_card.html?{q}")
    page.wait_for_function("() => document.getElementById('demo-card')?.contentDocument?.documentElement.dataset.ready === '1'")
elif act == "card_off":
    page.evaluate(CARD_JS, None)
```
Tested: the title card and the lower third render over the running app, the lower third is transparent, `card_off` removes it. Add `?anim=0` for stills. In `CAPTION_JS`, change the font to `600 40px/1.25 "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif`. Offline alternative: open `docs/style/title_card.html?...` (fonts load from `../../swapprint/fonts/`) in its own Playwright page and concatenate with ffmpeg.

## Do / don't

* Do: one accent (purple), magenta only for alerts, grays for everything else, left-aligned sentence-case text, square corners, ≥ 4.5:1 text contrast (white on `#8a3ffc` is 5.0, `#ee5396` on white is only 3.3: graphics, never text).
* Do: label every figure with what was measured and the conditions; keep the real numbers.
* Don't: IBM logos, the 8-bar mark, "IBM Quantum" marks or wordmarks, screenshots of IBM sites, wording such as "built with/for IBM", "official" or "powered by IBM". Naming "Qiskit Fall Fest 2026" or "IBM Plex" is factual and fine.
* Don't: rainbow colormaps, drop shadows, gradients except the 8 px bar in `title_card.html`, rounded cards, emoji in figures or cards.
* Don't edit the TTFs or rename them (OFL Reserved Font Name "Plex").

## Licence credits (paste into README)

> **Design and type.** Colour and spacing tokens follow the [Carbon Design System](https://carbondesignsystem.com) (© IBM Corp., Apache-2.0). Text is set in [IBM Plex](https://github.com/IBM/plex) (© 2017 IBM Corp., SIL Open Font License 1.1; the licence ships in `swapprint/fonts/OFL.txt`). The accent purple is taken from the event website q-bits.in. SwapPrint is an independent project by team sardines and is not made or endorsed by IBM.

`style.credit()` returns a one-line version for video end cards.

## pyproject.toml needs

```toml
[tool.setuptools.package-data]
swapprint = ["fonts/*.ttf", "fonts/OFL.txt"]
```
