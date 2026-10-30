"""Record a clean raw take of the SwapPrint app for the keynote finishing pass (video/finish.py).

    python video/record.py [--url=http://localhost:8601] [--no-warmup]

Uses the system Python (it has Playwright). Starts the app headless on port 8601 with the repo .venv unless --url
points at one that is already running, then performs the 'app' segments of video/timeline.json (the action
vocabulary of Ansh's app/demo/record_demo.py, plus scroll_to_target) with no captions or cards.

Capture: Chrome DevTools screencast at device scale 2 (3840x2160 JPEG frames, timestamped by the browser), so
finish.py can zoom up to 2x with no upscaling. Writes video/out/raw/:
  frames/*.jpg  take.json (frame times, per-segment action times, clicks, target boxes in CSS px)
  facts.json, art.png, mosaic*.png (from video/probe.py, run with the repo .venv)
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RAW = HERE / "out" / "raw"
W, H, DPR = 1920, 1080, 2
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
IMG_IFRAME = 'iframe[title*="streamlit_image_coordinates"]'

# Recording-only CSS (the app is not modified): no scrollbars, no Streamlit chrome, no stale-element dimming.
CLEAN_CSS = """
::-webkit-scrollbar { display: none !important; width: 0 !important; height: 0 !important; }
* { scrollbar-width: none !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stHeader"] { opacity: 0 !important; }
[data-testid="stStatusWidget"] { opacity: 0 !important; }
[data-stale="true"], .stale-element { opacity: 1 !important; transition: none !important; }
"""

IDLE_JS = """
() => {
  const s = document.querySelector('[data-testid="stStatusWidget"]');
  if (s && /Running|Connecting/i.test(s.innerText || s.textContent || '')) return false;
  if (document.querySelector('[data-testid="stSpinner"]')) return false;
  if (document.querySelector('[data-testid="stSkeleton"]')) return false;
  return true;
}
"""

# Locate a target and return its viewport box {x, y, w, h} in CSS px (null if not found / not visible).
FIND_JS = r"""
(spec) => {
  const vis = (el) => { const r = el.getBoundingClientRect();
    return r.width > 2 && r.height > 2 && r.bottom > 0 && r.top < innerHeight && getComputedStyle(el).visibility !== 'hidden'; };
  const box = (r) => ({x: r.left, y: r.top, w: r.width, h: r.height});
  const union = (els) => { let a = null; for (const el of els) { const r = el.getBoundingClientRect();
      a = a ? {l: Math.min(a.l, r.left), t: Math.min(a.t, r.top), r: Math.max(a.r, r.right), b: Math.max(a.b, r.bottom)}
            : {l: r.left, t: r.top, r: r.right, b: r.bottom}; }
    return a && {x: a.l, y: a.t, w: a.r - a.l, h: a.b - a.t}; };
  const panel = [...document.querySelectorAll('[role="tabpanel"]')].find((p) => p.offsetParent !== null) || document;
  let els = [];
  if (spec.iframe !== undefined) {
    els = [...document.querySelectorAll('iframe[title*="streamlit_image_coordinates"]')].filter(vis);
    els = els.slice(spec.iframe, spec.iframe + 1);
  } else if (spec.img_caption !== undefined) {
    const imgs = [...panel.querySelectorAll('[data-testid="stImage"], [data-testid="stFullScreenFrame"]')].filter(vis);
    for (const im of imgs) {
      const cap = im.querySelector('[data-testid="stImageCaption"], [data-testid="stCaptionContainer"], figcaption');
      const t = ((cap && cap.innerText) || im.innerText || '').trim();
      if (spec.exact ? t === spec.img_caption : t.includes(spec.img_caption)) {
        const img = im.querySelector('img'); els = [img || im]; break; }
    }
  } else if (spec.image_before_text !== undefined) {
    const caps = [...panel.querySelectorAll('[data-testid="stCaptionContainer"], [data-testid="stCaption"], p, div')]
      .filter((e) => e.children.length < 3 && (e.innerText || '').includes(spec.image_before_text));
    const cap = caps[caps.length - 1];
    if (cap) {
      const imgs = [...panel.querySelectorAll('[data-testid="stImage"] img, img')];
      let best = null;
      for (const im of imgs) if (cap.compareDocumentPosition(im) & Node.DOCUMENT_POSITION_PRECEDING) best = im;
      if (best) els = [best];
    }
  } else if (spec.text_block !== undefined) {
    // the smallest visible element whose own text starts with / contains the string
    const all = [...panel.querySelectorAll('div, p, h1, h2, h3, h4, span')].filter((e) =>
      (e.innerText || '').trim().startsWith(spec.text_block) && vis(e));
    all.sort((a, b) => (a.innerText.length - b.innerText.length));
    if (all.length) els = [all[0]];
  } else if (spec.sel !== undefined) {
    els = [...panel.querySelectorAll(spec.sel)].filter(vis);
    if (spec.text) els = els.filter((e) => (e.innerText || '').includes(spec.text));
    if (!spec.all) els = els.slice(spec.nth || 0, (spec.nth || 0) + 1);
  }
  if (spec.scroll && els.length) return els[0];
  return els.length ? union(els) : null;
}
"""


def log(msg: str) -> None:
    print(msg, flush=True)


def wait_idle(page: Page, timeout: float = 180.0, settle: float = 0.6) -> None:
    page.wait_for_timeout(300)
    deadline = time.monotonic() + timeout
    idle_since = None
    while time.monotonic() < deadline:
        if page.evaluate(IDLE_JS):
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since >= settle:
                return
        else:
            idle_since = None
        page.wait_for_timeout(120)
    log(f"  warning: app still busy after {timeout:.0f}s")


def scroll_main(page: Page, js_body: str, arg=None) -> None:
    page.evaluate("""([body, arg]) => { const m = document.querySelector('[data-testid="stMain"]') ||
                     document.querySelector('section.main') || document.scrollingElement; (new Function('m', 'arg', body))(m, arg); }""",
                  [js_body, arg])


def scroll_top(page: Page) -> None:
    page.evaluate("""() => { for (const el of document.querySelectorAll('[data-testid="stMain"], section.main, [data-testid="stAppViewContainer"]'))
                       el.scrollTo({top: 0, behavior: 'instant'}); window.scrollTo(0, 0); }""")


def find_box(page: Page, spec) -> dict | None:
    """A target spec (or a list of them, unioned) -> viewport box in CSS px."""
    specs = spec if isinstance(spec, list) else [spec]
    boxes = []
    for s in specs:
        if "iframe" in s:  # iframes need no panel filter, handled in JS
            pass
        b = page.evaluate(FIND_JS, s)
        if b:
            boxes.append(b)
    if not boxes:
        return None
    x0 = min(b["x"] for b in boxes); y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes); y1 = max(b["y"] + b["h"] for b in boxes)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def center(box) -> list[float] | None:
    return [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2] if box else None


def do_action(page: Page, step: dict) -> list[float] | None:
    """Perform one storyboard action instantly (scrolls are instant: finish.py dissolves between shots).
    Returns the click point in viewport CSS px, if the action clicked something."""
    act = step.get("action", "wait")
    sidebar = page.locator('[data-testid="stSidebar"]')
    click = None
    if act == "goto_tab":
        tab = page.get_by_role("tab", name=step["tab"], exact=True)
        click = center(tab.bounding_box())
        tab.click()
        scroll_top(page)
    elif act == "click_button":
        if step.get("scroll_first"):
            scroll_top(page)
        btn = page.get_by_role("button", name=step["name"], exact=step.get("exact", True)).filter(visible=True).first
        btn.wait_for(state="visible", timeout=20_000)
        btn.scroll_into_view_if_needed()
        click = center(btn.bounding_box())
        btn.click()
    elif act == "select_sidebar":
        box = sidebar.locator('[data-testid="stSelectbox"]').filter(has_text=step["label"]).first
        current = box.get_by_role("combobox")
        if step["option"].lower() not in (box.inner_text() + " " + (current.input_value() or "")).lower():
            current.click()
            page.get_by_role("option", name=step["option"]).first.click()
            click = center(box.bounding_box())
    elif act == "radio_sidebar":
        group = sidebar.locator('[data-testid="stRadio"]').filter(has_text=step["label"]).first
        opt = group.get_by_text(step["option"], exact=True)
        click = center(opt.bounding_box())
        opt.click()
    elif act == "click_image":
        sel = f'{IMG_IFRAME} >> visible=true >> nth={int(step.get("index", 0))}'
        page.locator(sel).scroll_into_view_if_needed()
        img = page.frame_locator(sel).locator("img")
        img.wait_for(state="visible", timeout=20_000)
        # The app's desktop CSS zoom makes Playwright's nested image box too
        # large. The iframe box remains in viewport coordinates; use it for
        # both the actual mouse click and the finishing pass's click marker.
        frame = page.locator(sel).bounding_box()
        if frame is None:
            raise RuntimeError("Clickable image iframe has no viewport box")
        click = [frame["x"] + frame["width"] * float(step["x"]),
                 frame["y"] + frame["height"] * float(step["y"])]
        page.mouse.click(*click)
    elif act == "scroll_to_text":
        target = page.get_by_text(step["text"]).filter(visible=True).first
        target.wait_for(state="visible", timeout=20_000)
        target.evaluate("el => el.scrollIntoView({block: 'start', behavior: 'instant'})")
        scroll_main(page, "m && m.scrollBy({top: -arg, behavior: 'instant'})", int(step.get("margin", 90)))
    elif act == "scroll_to_target":
        page.evaluate("""([js, spec]) => { const el = (eval(js))({...spec, scroll: true});
                          if (el && el.scrollIntoView) el.scrollIntoView({block: 'start', behavior: 'instant'}); }""",
                      [FIND_JS, step["target"]])
        scroll_main(page, "m && m.scrollBy({top: -arg, behavior: 'instant'})", int(step.get("margin", 90)))
    elif act == "wait":
        pass
    else:
        raise ValueError(f"unknown action {act!r}")
    return click


def vo_seconds(seg: dict) -> float:
    if "hold" in seg:
        return float(seg["hold"])
    if seg.get("show") is False:
        return 0.5
    words = len((seg.get("tts") or seg.get("vo") or "").split())
    return words / 2.4 + 1.6


def app_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/_stcore/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


class Screencast:
    """CDP screencast -> timestamped JPEGs on disk."""

    def __init__(self, ctx, page, out: Path):
        self.out, self.frames, self.cdp = out, [], ctx.new_cdp_session(page)
        out.mkdir(parents=True, exist_ok=True)
        self.cdp.on("Page.screencastFrame", self._on)
        self.running = False

    def _on(self, f):
        n = len(self.frames)
        name = f"{n:06d}.jpg"
        (self.out / name).write_bytes(base64.b64decode(f["data"]))
        self.frames.append([f["metadata"]["timestamp"], name, time.time()])
        if self.running:
            try:
                self.cdp.send("Page.screencastFrameAck", {"sessionId": f["sessionId"]})
            except Exception:
                pass

    def start(self):
        self.running = True
        self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 93,
                                               "maxWidth": W * DPR, "maxHeight": H * DPR, "everyNthFrame": 1})

    def stop(self):
        self.running = False
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass


def new_page(browser, base_url: str):
    ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=DPR)
    page = ctx.new_page()
    page.set_default_timeout(20_000)
    parts = urllib.parse.urlsplit(base_url)
    query = dict(urllib.parse.parse_qsl(parts.query, keep_blank_values=True))
    query["welcome"] = "closed"
    page.goto(urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query))))
    page.get_by_role("tab", name="1 · Fingerprint").wait_for(timeout=180_000)
    page.add_style_tag(content=CLEAN_CSS)
    wait_idle(page)
    return ctx, page


def run_segments(page: Page, segs: list[dict], hold: bool, cast: Screencast | None = None) -> dict:
    beats = {}
    for i, seg in enumerate(segs, 1):
        t0 = time.time()
        log(f"[{i:2d}/{len(segs)}] {seg['id']}")
        acts = []
        for step in seg.get("actions", []):
            a0 = time.time()
            try:
                click_pt = do_action(page, step)
            except Exception as exc:
                raise RuntimeError(f"segment {seg['id']}: action {step.get('action')} failed") from exc
            ac = time.time()
            marks = {}
            if step.get("watch"):   # log when the n-th matching element appears (e.g. the n-th SWAP-test shot)
                sel, want = step["watch"]["sel"], sorted(step["watch"]["counts"])
                end, reset = time.monotonic() + 8, False
                while want and time.monotonic() < end:
                    n = page.evaluate("(s) => document.querySelectorAll(s).length", sel)
                    reset = reset or n < want[0] or n <= 1   # wait for the restart before counting up
                    while reset and want and n >= want[0]:
                        marks[str(want.pop(0))] = time.time()
                    page.wait_for_timeout(15)
            wait_idle(page)
            acts.append({"t0": a0, "t_click": ac, "t_idle": time.time(), "click": click_pt, "action": step.get("action"),
                         "marks": marks})
        page.add_style_tag(content=CLEAN_CSS)  # harmless if already there
        targets = {}
        for name, spec in (seg.get("targets") or {}).items():
            try:
                targets[name] = find_box(page, spec)
            except Exception as exc:
                log(f"  target {name} failed: {exc}")
                targets[name] = None
            if targets[name] is None:
                log(f"  target {name} not found")
        text = page.evaluate("() => (document.querySelector('[data-testid=\"stMain\"]') || document.body).innerText")
        if hold:
            remain = vo_seconds(seg) + 1.0 - (time.time() - (acts[-1]["t_idle"] if acts else t0))
            if seg.get("clip"):
                remain += 0.5
            page.wait_for_timeout(int(max(remain, 1.5) * 1000))
        beats[seg["id"]] = {"t0": t0, "t1": time.time(), "actions": acts, "targets": targets, "text": text[:6000]}
    return beats


def main() -> None:
    url = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--url=")), "http://localhost:8601")
    timeline = json.loads((HERE / "timeline.json").read_text(encoding="utf-8"))
    meta = timeline["meta"]
    segs = [s for s in timeline["segments"] if s["type"] == "app"]

    shutil.rmtree(RAW, ignore_errors=True)
    RAW.mkdir(parents=True)
    log("probe: computing facts with the repo .venv")
    subprocess.run([str(VENV_PY), str(HERE / "probe.py"), meta["artwork"], str(meta["seed"]), str(RAW)], check=True,
                   cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"}, stdout=subprocess.DEVNULL)

    server = None
    if not app_running(url):
        port = url.rsplit(":", 1)[-1].strip("/")
        log(f"starting the app on port {port}")
        server = subprocess.Popen([str(VENV_PY), "-m", "streamlit", "run", "app/streamlit_app.py", "--server.headless",
                                   "true", "--server.port", port], cwd=ROOT,
                                  env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(240):
            if app_running(url):
                break
            time.sleep(0.5)
        else:
            raise SystemExit("the app did not start")
    try:
        with sync_playwright() as p:
            # --force-device-scale-factor makes the screencast deliver 3840x2160 frames (plain dpr=2 gives 1920x1080)
            browser = p.chromium.launch(args=[f"--force-device-scale-factor={DPR}", "--hide-scrollbars"])
            if "--no-warmup" not in sys.argv:
                log("warm-up pass (not recorded): fills the app's caches so the take has no long waits")
                ctx, page = new_page(browser, url)
                run_segments(page, segs, hold=False)
                ctx.close()
            log("recording")
            ctx, page = new_page(browser, url)
            cast = Screencast(ctx, page, RAW / "frames")
            cast.start()
            page.wait_for_timeout(1200)
            t_start = time.time()
            beats = run_segments(page, segs, hold=True, cast=cast)
            page.wait_for_timeout(800)
            cast.stop()
            page.wait_for_timeout(300)
            ctx.close()
            browser.close()
    finally:
        if server:
            server.terminate()

    # Browser frame timestamps and Python's clock can disagree: shift frames onto Python's clock using the
    # smallest receive delay seen (frames are acked one by one, so the fastest ones arrive within a few ms).
    if cast.frames:
        lag = sorted(r - ts for ts, _, r in cast.frames)
        offset = lag[min(len(lag) - 1, max(0, len(lag) // 20))] - 0.015
        cast.frames = [[ts + offset, name] for ts, name, _ in cast.frames]
        log(f"frame clock offset {offset:+.3f} s")
    take = {"size": [W, H], "dpr": DPR, "t_start": t_start, "frames": cast.frames, "beats": beats}
    (RAW / "take.json").write_text(json.dumps(take, indent=0), encoding="utf-8")
    dur = cast.frames[-1][0] - cast.frames[0][0] if cast.frames else 0
    log(f"wrote {len(cast.frames)} frames ({dur:.0f} s) and {RAW / 'take.json'}")
    missing = [f"{b}.{n}" for b, v in beats.items() for n, box in v["targets"].items() if box is None]
    if missing:
        log("targets not found (finish.py will not zoom there): " + ", ".join(missing))


if __name__ == "__main__":
    main()
