"""Record a captioned SwapPrint demo video from a storyboard.

Usage:  .venv/bin/python app/demo/record_demo.py [storyboard.json] [--url=http://localhost:8601] [--no-captions] [--steps=A-B] [--out=NAME]

Each storyboard step: {"say": caption, "action": <name>, ...args, "hold": seconds, "check": optional name}
Actions:
  goto_tab        tab            (tab label, e.g. "3 · Verify"; scrolls to the top first)
  click_button    name           (button label; optional "exact": false, "scroll_first": true)
  select_sidebar  label, option  (sidebar selectbox label; option text, substring match)
  radio_sidebar   label, option  (sidebar radio label; option text, exact)
  click_image     x, y           (fractions 0..1 of the image; optional "index" among visible clickable images)
  scroll_to_text  text           (scrolls the first visible match near the top of the window)
  card            kind, title, sub, kicker, num, foot  (full-screen title_card.html iframe; use "say": "")
  card_off        (remove the card)
  wait            (nothing, just hold)
"check": "name" saves out/check_<name>.png, a frame from the finished video at the end of that step.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlencode

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
W, H = 1920, 1080
IMG_IFRAME = 'iframe[title*="streamlit_image_coordinates"]'

CAPTION_JS = """
(text) => {
  let bar = document.getElementById('demo-caption');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'demo-caption';
    Object.assign(bar.style, {
      position: 'fixed', left: '0', right: '0', bottom: '0', zIndex: '2147483647',
      padding: '22px 60px 26px', background: 'rgba(0,0,0,0.72)', color: '#fff',
      font: '600 40px/1.25 "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif',
      textAlign: 'center', pointerEvents: 'none', textShadow: '0 2px 4px rgba(0,0,0,0.6)'
    });
    document.body.appendChild(bar);
  }
  bar.textContent = text;
  bar.style.display = text ? 'block' : 'none';
}
"""

CARD_JS = """(src) => { let f = document.getElementById('demo-card');
  if (!src) { if (f) f.remove(); return; }
  if (!f) { f = document.createElement('iframe'); f.id = 'demo-card';
    Object.assign(f.style, {position:'fixed', inset:'0', width:'100vw', height:'100vh', border:'0', zIndex:'2147483646', background:'transparent'});
    document.body.appendChild(f); }
  f.src = src; }"""

IDLE_JS = """
() => {
  const s = document.querySelector('[data-testid="stStatusWidget"]');
  if (s && /Running|Connecting/i.test(s.innerText || '')) return false;
  if (document.querySelector('[data-testid="stSpinner"]')) return false;
  if (document.querySelector('[data-testid="stSkeleton"]')) return false;
  return true;
}
"""


def wait_idle(page: Page, timeout: float = 120.0, settle: float = 0.6) -> None:
    """Wait until Streamlit has finished rerunning (idle for `settle` seconds in a row)."""
    page.wait_for_timeout(300)  # give the status widget a moment to appear
    deadline = time.monotonic() + timeout
    idle_since = None
    while time.monotonic() < deadline:
        if page.evaluate(IDLE_JS):
            idle_since = idle_since or time.monotonic()
            if time.monotonic() - idle_since >= settle:
                return
        else:
            idle_since = None
        page.wait_for_timeout(150)
    print(f"  warning: app still busy after {timeout:.0f}s, continuing", file=sys.stderr)


def scroll_top(page: Page) -> None:
    page.evaluate("""() => {
      for (const el of document.querySelectorAll('[data-testid="stMain"], section.main, [data-testid="stAppViewContainer"]'))
        el.scrollTo({top: 0, behavior: 'instant'});
      window.scrollTo(0, 0);
    }""")


def visible(locator):
    return locator.filter(visible=True).first


def do_step(page: Page, step: dict, base_url: str = "http://localhost:8601") -> None:
    act = step.get("action", "wait")
    sidebar = page.locator('[data-testid="stSidebar"]')
    if act == "goto_tab":
        page.get_by_role("tab", name=step["tab"], exact=True).click()
        scroll_top(page)
    elif act == "click_button":
        if step.get("scroll_first"):
            scroll_top(page)
        btn = visible(page.get_by_role("button", name=step["name"], exact=step.get("exact", True)))
        btn.wait_for(state="visible", timeout=15_000)
        btn.scroll_into_view_if_needed()
        btn.click()
    elif act == "select_sidebar":
        box = sidebar.locator('[data-testid="stSelectbox"]').filter(has_text=step["label"]).first
        current = box.get_by_role("combobox")
        if step["option"].lower() not in (box.inner_text() + " " + (current.input_value() or "")).lower():
            current.click()
            page.get_by_role("option", name=step["option"]).first.click()
        else:  # already selected: just show the dropdown briefly for the viewer
            current.click()
            page.wait_for_timeout(1200)
            page.keyboard.press("Escape")
    elif act == "radio_sidebar":
        group = sidebar.locator('[data-testid="stRadio"]').filter(has_text=step["label"]).first
        group.get_by_text(step["option"], exact=True).click()
    elif act == "click_image":
        sel = f'{IMG_IFRAME} >> visible=true >> nth={int(step.get("index", 0))}'
        page.locator(sel).scroll_into_view_if_needed()
        img = page.frame_locator(sel).locator("img")
        img.wait_for(state="visible", timeout=15_000)
        box = img.bounding_box()
        img.click(position={"x": box["width"] * float(step["x"]), "y": box["height"] * float(step["y"])})
    elif act == "scroll_to_text":
        target = visible(page.get_by_text(step["text"]))
        target.wait_for(state="visible", timeout=15_000)
        target.evaluate("el => el.scrollIntoView({block: 'start', behavior: 'smooth'})")
        page.wait_for_timeout(700)
        # leave a little room above the target
        page.evaluate("""() => { const m = document.querySelector('[data-testid="stMain"]');
                                 if (m) m.scrollBy({top: -90, behavior: 'instant'}); }""")
    elif act == "card":  # {kind: title|section|lower|end, title, sub, kicker, num, foot, theme}
        q = urlencode({k: step[k] for k in ("kind", "title", "sub", "kicker", "num", "foot", "theme") if k in step},
                      quote_via=quote)
        page.evaluate(CARD_JS, f"{base_url}/app/static/title_card.html?{q}")
        page.wait_for_function("() => document.getElementById('demo-card')?.contentDocument?.documentElement?.dataset?.ready === '1'")
        return
    elif act == "card_off":
        page.evaluate(CARD_JS, None)
        return
    elif act == "wait":
        pass
    else:
        raise ValueError(f"unknown action {act!r}")
    wait_idle(page)


def srt_time(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def main() -> None:
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_captions = "--no-captions" in flags
    name = next((a.split("=", 1)[1] for a in flags if a.startswith("--out=")), "swapprint_demo")
    rng = next((a.split("=", 1)[1] for a in flags if a.startswith("--steps=")), None)
    url = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--url=")), "http://localhost:8601")
    board_path = Path(args[0]) if args else HERE / "storyboard.json"
    steps = json.loads(board_path.read_text(encoding="utf-8"))
    first, last = 1, len(steps)
    if rng:
        a, _, b = rng.partition("-")
        first, last = int(a), int(b or a)
        if not 1 <= first <= last <= len(steps):
            sys.exit(f"--steps={rng} is outside 1-{len(steps)}")
    cap = (lambda page, text: None) if no_captions else (lambda page, text: page.evaluate(CAPTION_JS, text))
    trim = [None, None]  # video seconds of the start of step `first` and the end of step `last`
    OUT.mkdir(parents=True, exist_ok=True)
    raw_dir = OUT / "_raw"
    shutil.rmtree(raw_dir, ignore_errors=True)

    cues, checks = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        # Warm-up visit (not recorded) so cached fingerprints don't slow the real take.
        warm = browser.new_page(viewport={"width": W, "height": H})
        warm.goto(url)
        warm.get_by_role("tab", name="1 · Fingerprint").wait_for(timeout=120_000)
        wait_idle(warm)
        warm.close()

        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(raw_dir),
                                  record_video_size={"width": W, "height": H})
        page = ctx.new_page()
        page.set_default_timeout(15_000)
        t0 = time.monotonic()  # video time 0 is ~ here
        page.goto(url)
        page.get_by_role("tab", name="1 · Fingerprint").wait_for(timeout=120_000)
        wait_idle(page)
        for i, step in enumerate(steps, 1):
            say = step.get("say", "")
            cap(page, say)
            start = time.monotonic() - t0
            if i == first:
                trim[0] = start
            print(f"[{i:2d}/{len(steps)}] {start:6.1f}s {step.get('action', 'wait')}: {say}")
            try:
                do_step(page, step, url)
            except Exception as exc:  # keep recording; one failed step should not lose the take
                print(f"  step {i} failed: {exc}", file=sys.stderr)
            cap(page, say)  # re-assert in case a rerun touched the DOM
            page.wait_for_timeout(int(float(step.get("hold", 3)) * 1000))
            end = time.monotonic() - t0
            cues.append((start, end, say))
            if i == last:
                trim[1] = end
            if step.get("check"):
                checks.append((step["check"], end - 0.5))
                page.screenshot(path=str(OUT / f"check_{step['check']}.png"))  # replaced by a video frame below
        cap(page, "")
        page.wait_for_timeout(500)
        video = Path(page.video.path())
        ctx.close()
        browser.close()

    webm = OUT / f"{name}.webm"
    shutil.move(str(video), webm)
    shutil.rmtree(raw_dir, ignore_errors=True)
    srt = OUT / ("captions.srt" if name == "swapprint_demo" else f"{name}.srt")
    off = trim[0] if rng else 0.0
    kept = [c for k, c in enumerate(cues, 1) if first <= k <= last and c[2]]
    with open(srt, "w", encoding="utf-8") as f:
        for n, (a, b, say) in enumerate(kept, 1):
            f.write(f"{n}\n{srt_time(a - off)} --> {srt_time(b - off)}\n{say}\n\n")
    print(f"wrote {webm} ({webm.stat().st_size / 1e6:.1f} MB; full take), {srt}")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        mp4 = OUT / f"{name}.mp4"
        cut = ["-ss", f"{trim[0]:.2f}", "-to", f"{trim[1]:.2f}"] if rng else []
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", *cut, "-i", str(webm), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-preset", "medium", "-crf", "20", "-movflags", "+faststart", "-an", str(mp4)], check=True)
        print(f"wrote {mp4} ({mp4.stat().st_size / 1e6:.1f} MB)")
        for cname, t in checks:  # real frames from the full recording
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", str(webm), "-frames:v", "1",
                            str(OUT / f"check_{cname}.png")], check=True)
    if checks:
        print("checks: " + ", ".join(str(OUT / f"check_{n}.png") for n, _ in checks))


if __name__ == "__main__":
    main()
