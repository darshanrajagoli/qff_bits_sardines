"""Keynote finishing pass: video/timeline.json + video/out/raw/ (from record.py) -> video/out/swapprint_demo.mp4.

    video/.venv/Scripts/python.exe video/finish.py              # full render
    video/.venv/Scripts/python.exe video/finish.py --stills 3,20,45   # QC stills (seconds) -> out/qc/, no encode
    options: --no-tts (captions only)  --no-music

Every frame is drawn here, in Python: Carbon g100 cards, the animated idea diagram and log-scale chart, figure cards,
and the app take with subpixel eased zooms (the take is 3840x2160, so zooms up to 2x are never upscaled). Motion uses
Carbon's curves (carbondesignsystem.com/elements/motion/overview): productive standard cubic-bezier(0.2, 0, 0.38, 0.9)
for camera and UI, expressive standard cubic-bezier(0.4, 0.14, 0.3, 1) for big reveals. Narration: edge-tts.
Music: an original pad synthesised below (no third-party audio). Colours and fonts: swapprint/style.py (read only).
"""
from __future__ import annotations

import asyncio
import bisect
import hashlib
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
import wave
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from difflib import SequenceMatcher

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "out"
RAW = OUT / "raw"
TTS_DIR = OUT / "tts"
NARRATION_CREDIT = "Narration: synthetic timing reference."
W, H = 1920, 1080
SR = 48000

_spec = importlib.util.spec_from_file_location("sp_style", ROOT / "swapprint" / "style.py")
style = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(style)          # style.py imports nothing heavy at module level
G = style.THEMES["g100"]
C = style.CARBON


def rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


BG = rgb(G["background"])                # #161616
LAYER1 = rgb(G["layer-01"])              # #262626
LAYER2 = rgb(G["layer-02"])              # #393939
TXT = rgb(G["text-primary"])             # #f4f4f4
TXT2 = rgb(G["text-secondary"])          # #c6c6c6
HELP = rgb(G["text-helper"])             # #a8a8a8
BORDER = rgb(G["border-subtle-01"])      # #525252
ACCENT = rgb(style.PURPLE)               # #8a3ffc
ACCENT_D = rgb(style.ACCENT_ON_DARK)     # #a56eff
ALERT = rgb(style.ALERT_ON_DARK)         # #ff7eb6
ALERT50 = rgb(style.ALERT)               # #ee5396
GRAD = [rgb(c) for c in style.WEBSITE_GRADIENT]
FONTS = style.font_paths()


# ------------------------------------------------------------------ easing (Carbon motion)

def bezier(p1x, p1y, p2x, p2y):
    def f(t: float) -> float:
        t = min(1.0, max(0.0, t))
        lo, hi = 0.0, 1.0
        for _ in range(30):   # solve x(s) = t by bisection, return y(s)
            s = (lo + hi) / 2
            x = 3 * (1 - s) ** 2 * s * p1x + 3 * (1 - s) * s * s * p2x + s ** 3
            lo, hi = (s, hi) if x < t else (lo, s)
        s = (lo + hi) / 2
        return 3 * (1 - s) ** 2 * s * p1y + 3 * (1 - s) * s * s * p2y + s ** 3
    return f


PRODUCTIVE = bezier(0.2, 0, 0.38, 0.9)
EXPRESSIVE = bezier(0.4, 0.14, 0.3, 1)
ENTRANCE = bezier(0, 0, 0.3, 1)          # expressive entrance


_LUT_X = np.linspace(0, 1, 513)


@lru_cache(maxsize=8)
def _lut(ease):
    return np.array([ease(x) for x in _LUT_X], np.float32)


def ease_arr(ease, x: np.ndarray) -> np.ndarray:
    return np.interp(np.clip(x, 0, 1), _LUT_X, _lut(ease)).astype(np.float32)


def prog(u, t0, dur, ease=PRODUCTIVE):
    if dur <= 0:
        return 1.0 if u >= t0 else 0.0
    return ease((u - t0) / dur)


def lerp(a, b, k):
    return a + (b - a) * k


# ------------------------------------------------------------------ drawing primitives (float32 RGB canvas, 0..255)

def canvas(color=BG) -> np.ndarray:
    c = np.empty((H, W, 3), np.float32)
    c[:] = color
    return c


@lru_cache(maxsize=4)
def grid_bg() -> np.ndarray:
    """g100 with the event site's faint 40 px circuit grid (purple at 8 %), as in docs/style/title_card.html."""
    c = canvas()
    a = 0.08
    for x in range(0, W, 40):
        c[:, x] = c[:, x] * (1 - a) + np.array(ACCENT) * a
    for y in range(20, H, 40):
        c[y, :] = c[y, :] * (1 - a) + np.array(ACCENT) * a
    return c


@lru_cache(maxsize=64)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS[name]), size)


@lru_cache(maxsize=512)
def text_layer(s: str, name: str = "IBMPlexSans-Regular", size: int = 40, color=TXT, track: float = 0.0):
    """RGBA float layer of one line of text; (0, 0) is the top of the ascender line."""
    f = font(name, size)
    asc, desc = f.getmetrics()
    if track:
        widths = [f.getlength(ch) + track for ch in s]
        w = int(math.ceil(sum(widths))) + 4
    else:
        w = int(math.ceil(f.getlength(s))) + 4
    im = Image.new("L", (max(w, 1), asc + desc + 2), 0)
    d = ImageDraw.Draw(im)
    if track:
        x = 0.0
        for ch, cw in zip(s, widths):
            d.text((x, 0), ch, font=f, fill=255)
            x += cw
    else:
        d.text((0, 0), s, font=f, fill=255)
    a = np.asarray(im, np.float32) / 255.0
    lay = np.empty(a.shape + (4,), np.float32)
    lay[..., :3] = color
    lay[..., 3] = a
    return lay


def text_w(s, name="IBMPlexSans-Regular", size=40):
    return font(name, size).getlength(s)


def blit(dst: np.ndarray, lay: np.ndarray, x: float, y: float, op: float = 1.0) -> None:
    """Alpha-composite an RGBA float layer at a subpixel position."""
    if op <= 0.002:
        return
    fx, fy = x - math.floor(x), y - math.floor(y)
    if fx > 0.02 or fy > 0.02:
        h, w = lay.shape[:2]
        m = np.float32([[1, 0, fx], [0, 1, fy]])
        lay = cv2.warpAffine(lay, m, (w + 1, h + 1), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                             borderValue=(0, 0, 0, 0))
    x, y = int(math.floor(x)), int(math.floor(y))
    h, w = lay.shape[:2]
    x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, W), min(y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    sub = lay[y0 - y:y1 - y, x0 - x:x1 - x]
    a = sub[..., 3:4] * op
    region = dst[y0:y1, x0:x1]
    region *= (1 - a)
    region += sub[..., :3] * a


def rect(dst, x, y, w, h, color, op=1.0):
    x0, y0 = int(round(x)), int(round(y))
    x1, y1 = int(round(x + w)), int(round(y + h))
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 <= x0 or y1 <= y0 or op <= 0:
        return
    dst[y0:y1, x0:x1] = dst[y0:y1, x0:x1] * (1 - op) + np.array(color, np.float32) * op


def frame_rect(dst, x, y, w, h, color, t=2, op=1.0):
    rect(dst, x, y, w, t, color, op); rect(dst, x, y + h - t, w, t, color, op)
    rect(dst, x, y, t, h, color, op); rect(dst, x + w - t, y, t, h, color, op)


def gradient_bar(dst, x, y, w, h=8, op=1.0, k=1.0):
    """The event site's .text-gradient (#ff7eb6 0 %, #ee5396 42 %, #8a3ffc 100 %): the one gradient the kit allows."""
    ww = max(1, int(w * k))
    xs = np.linspace(0, 1, int(w))[:ww]
    cols = np.empty((ww, 3), np.float32)
    for i, v in enumerate(xs):
        if v < 0.42:
            cols[i] = np.array(GRAD[0]) + (np.array(GRAD[1]) - GRAD[0]) * (v / 0.42)
        else:
            cols[i] = np.array(GRAD[1]) + (np.array(GRAD[2]) - GRAD[1]) * ((v - 0.42) / 0.58)
    x0, y0 = int(x), int(y)
    if op > 0 and ww > 0:
        dst[y0:y0 + h, x0:x0 + ww] = dst[y0:y0 + h, x0:x0 + ww] * (1 - op) + cols[None] * op


def line(dst, p, q, color, th=2, op=1.0):
    pad_ = th + 3
    x0, y0 = int(max(min(p[0], q[0]) - pad_, 0)), int(max(min(p[1], q[1]) - pad_, 0))
    x1, y1 = int(min(max(p[0], q[0]) + pad_ + 1, W)), int(min(max(p[1], q[1]) + pad_ + 1, H))
    if x1 <= x0 or y1 <= y0 or op <= 0:
        return
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.line(m, (int((p[0] - x0) * 4), int((p[1] - y0) * 4)), (int((q[0] - x0) * 4), int((q[1] - y0) * 4)), 255, th,
             cv2.LINE_AA, shift=2)
    a = (m.astype(np.float32) / 255.0 * op)[..., None]
    reg = dst[y0:y1, x0:x1]
    reg *= (1 - a)
    reg += np.array(color, np.float32) * a


def ring(dst, cx, cy, r, color, th=3, op=1.0, fill=False):
    x0, y0 = int(max(cx - r - th - 2, 0)), int(max(cy - r - th - 2, 0))
    x1, y1 = int(min(cx + r + th + 3, W)), int(min(cy + r + th + 3, H))
    if x1 <= x0 or y1 <= y0:
        return
    m = np.zeros((y1 - y0, x1 - x0), np.uint8)
    cv2.circle(m, (int((cx - x0) * 4), int((cy - y0) * 4)), int(r * 4), 255, -1 if fill else th, cv2.LINE_AA, shift=2)
    a = (m.astype(np.float32) / 255.0 * op)[..., None]
    reg = dst[y0:y1, x0:x1]
    reg *= (1 - a)
    reg += np.array(color, np.float32) * a


def ket(dst, x, y, inner, size, color=TXT, op=1.0, name="IBMPlexSans-Regular"):
    """|inner> with a drawn right angle bracket (Plex has no U+27E9). Returns the width."""
    bar = text_layer("|", name, size, color)
    blit(dst, bar, x, y, op)
    lay = text_layer(inner, name, size, color)
    ix = x + text_w("|", name, size) + size * 0.06
    blit(dst, lay, ix, y, op)
    asc = font(name, size).getmetrics()[0]
    bx = ix + text_w(inner, name, size) + size * 0.08
    top, bot = y + asc * 0.22, y + asc * 1.12
    mid = (top + bot) / 2
    th = max(2, int(size / 18))
    line(dst, (bx, top), (bx + size * 0.22, mid), color, th, op)
    line(dst, (bx + size * 0.22, mid), (bx, bot), color, th, op)
    return bx + size * 0.3 - x


def image_layer(img: np.ndarray, w: int, h: int, interp=cv2.INTER_AREA) -> np.ndarray:
    im = cv2.resize(img, (w, h), interpolation=interp).astype(np.float32)
    lay = np.empty((h, w, 4), np.float32)
    lay[..., :3] = im[..., :3]
    lay[..., 3] = 1.0
    return lay


def rise(dst, lay, x, y, u, t0, dur=0.4, dist=16, ease=ENTRANCE, op=1.0):
    """Carbon-style entrance: fade + 16 px rise."""
    k = prog(u, t0, dur, ease)
    if k > 0:
        blit(dst, lay, x, y + dist * (1 - k), op * k)


def wrap(s: str, name: str, size: int, max_w: float) -> list[str]:
    out, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word).strip()
        if text_w(trial, name, size) <= max_w or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


# ------------------------------------------------------------------ data

def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


TL = load_json(HERE / "timeline.json")
META = TL["meta"]
FPS = int(META.get("fps", 30))
XF = float(META.get("crossfade", 0.45))
FACTS = load_json(RAW / "facts.json")
TAKE = load_json(RAW / "take.json") if (RAW / "take.json").exists() else None
ART = np.asarray(Image.open(RAW / "art.png").convert("RGB"))
MOSAIC = np.asarray(Image.open(RAW / "mosaic.png").convert("RGB"))
NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine",
             10: "ten", 11: "eleven", 12: "twelve"}


def fmt_vars() -> dict:
    v = dict(FACTS)
    v["strict_first_shot_word"] = NUM_WORDS.get(FACTS.get("strict_first_shot"), str(FACTS.get("strict_first_shot")))
    v["strict_99"] = f"{FACTS['strict_99']:.0f}" if FACTS.get("strict_99") else "a few"
    m = (FACTS.get("frqi_99") or 0) / 1e6
    v["frqi_99_words"] = f"{m:.1f} million"
    return v


def codeword_bits(key: str) -> np.ndarray:
    return np.unpackbits(np.frombuffer(bytes.fromhex(FACTS[key]), np.uint8))[:2048]


# ------------------------------------------------------------------ narration (edge-tts) and captions

def tts(text: str, voice: str, rate: str) -> tuple[np.ndarray, list]:
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{voice}|{rate}|{text}".encode()).hexdigest()[:16]
    mp3, js, wav_p = TTS_DIR / f"{key}.mp3", TTS_DIR / f"{key}.json", TTS_DIR / f"{key}.wav"
    if not (mp3.exists() and js.exists()):
        import edge_tts

        async def go():
            comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
            audio, words = bytearray(), []
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    audio += ch["data"]
                elif ch["type"] == "WordBoundary":
                    words.append([ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"]])
            return bytes(audio), words
        audio, words = asyncio.run(go())
        mp3.write_bytes(audio)
        js.write_text(json.dumps(words), encoding="utf-8")
    if not wav_p.exists():
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-ac", "1", "-ar", str(SR), str(wav_p)],
                       check=True)
    with wave.open(str(wav_p)) as wf:
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768.0
    return pcm, load_json(js)


def fake_words(text: str) -> list:
    t, out = 0.2, []
    for w in text.split():
        d = 0.08 + 0.055 * len(w)
        out.append([t, d, w.strip(",.;:?!")])
        t += d + (0.35 if w[-1] in ".?!:" else 0.12 if w[-1] == "," else 0.05)
    return out


def human_clip(manifest_path, item):
    path = manifest_path.parent / item["audio"]
    with wave.open(str(path)) as wf:
        if (wf.getframerate(), wf.getnchannels(), wf.getsampwidth()) != (SR, 1, 2):
            raise ValueError(f"Human clip must be mono 48 kHz 16-bit PCM: {path}")
        pcm = np.frombuffer(wf.readframes(wf.getnframes()), np.int16).astype(np.float32) / 32768
    words = item["words"]
    if not words or any(a < 0 or d <= 0 or a+d > len(pcm)/SR + .25 for a, d, _ in words):
        raise ValueError(f"Review human word timings for {path}")
    return pcm, words


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9]", "", w.lower())


def word_time(words: list, query: str, after: float = -1.0, end: bool = False) -> float | None:
    q = norm(query)
    for off, dur, w in words:
        if off > after and norm(w).startswith(q):
            return off + dur if end else off
    return None


def caption_chunks(caption: str, words: list) -> list:
    """Sentences (long ones split at commas/colons) timed by mapping caption word positions onto the TTS words."""
    sents = [s for s in re.split(r"(?<=[.?!])\s+", caption.strip()) if s]
    chunks = []
    for s in sents:
        if len(s) <= 78:
            chunks.append(s)
            continue
        parts = re.split(r"(?<=[,:])\s+", s)
        cur = ""
        for p_ in parts:
            if cur and len(cur) + len(p_) > 70:
                chunks.append(cur)
                cur = p_
            else:
                cur = (cur + " " + p_).strip()
        if cur:
            chunks.append(cur)
    caption_words = [norm(word) for chunk in chunks for word in chunk.split()]
    spoken_words = [norm(word[2]) for word in words]
    alignment = {}
    for tag, a0, a1, b0, b1 in SequenceMatcher(None, caption_words, spoken_words, autojunk=False).get_opcodes():
        for index in range(a0, a1):
            offset = index - a0 if tag == "equal" else int((index - a0) * (b1 - b0) / max(a1 - a0, 1))
            alignment[index] = min(max(0, b0 + offset), max(0, len(words) - 1))
    out, a = [], 0
    for c in chunks:
        j = alignment.get(a, 0)
        out.append([words[j][0] if words else 0.0, c])
        a += len(c.split())
    ends = [o[0] for o in out[1:]] + [words[-1][0] + words[-1][1] + 0.5 if words else 3.0]
    return [[s - 0.05, e - 0.05, c] for (s, c), e in zip(out, ends)]


# ------------------------------------------------------------------ app take

class Take:
    def __init__(self, take: dict):
        self.times = [f[0] for f in take["frames"]]
        self.files = [RAW / "frames" / f[1] for f in take["frames"]]
        self.beats = take["beats"]
        self.dpr = take.get("dpr", 2)
        self._cache: dict = {}

    def frame(self, t: float) -> tuple[int, np.ndarray]:
        i = max(0, bisect.bisect_right(self.times, t) - 1)
        if i not in self._cache:
            if len(self._cache) > 6:
                self._cache.pop(next(iter(self._cache)))
            im = cv2.imread(str(self.files[i]), cv2.IMREAD_COLOR)
            self._cache[i] = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
        return i, self._cache[i]

    def resolve(self, bid: str, expr) -> float:
        b = self.beats[bid]
        if isinstance(expr, (int, float)):
            return b["t0"] + float(expr)
        m = re.match(r"(click|idle|start|mark):(\d+)(?::(\w+))?\s*([+-]\s*[\d.]+)?", str(expr))
        kind, n, mk, off = m.group(1), int(m.group(2)), m.group(3), float((m.group(4) or "0").replace(" ", ""))
        a = b["actions"][min(n, len(b["actions"]) - 1)]
        if kind == "mark":
            return (a.get("marks") or {}).get(mk, a["t_click"] + 0.3) + off
        return {"click": a["t_click"], "idle": a["t_idle"], "start": a["t0"]}[kind] + off


_view_cache: dict = {}


def render_view(src: np.ndarray, fid: int, cam: tuple) -> np.ndarray:
    """cam = (cx, cy, s) in CSS px of the 1920x1080 viewport; s = zoom. Supersampled crop: warp at 2x, area-downscale."""
    cx, cy, s = cam
    if abs(s - 1) < 1e-3 and abs(cx - 960) < 0.05 and abs(cy - 540) < 0.05:
        if _view_cache.get("id") != fid:
            _view_cache.update(id=fid, img=cv2.resize(src, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32))
        return _view_cache["img"].copy()
    sh, sw = src.shape[:2]
    k = sw / W                                 # source px per CSS px (2)
    x0, y0 = (cx - W / (2 * s)) * k, (cy - H / (2 * s)) * k
    m = np.float32([[1 / s, 0, x0], [0, 1 / s, y0]])   # intermediate (2W x 2H) -> source
    big = cv2.warpAffine(src, m, (sw, sh), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                         borderMode=cv2.BORDER_REPLICATE)
    return cv2.resize(big, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)


def cam_for_box(box: dict, scale_cap: float, pad: float = 40, focus=None) -> tuple:
    if focus is not None:
        fy, fx = focus
        cx = box["x"] + (fx + 2) / 256 * box["w"]
        cy = box["y"] + (fy + 2) / 256 * box["h"]
        s = scale_cap
    else:
        cx, cy = box["x"] + box["w"] / 2, box["y"] + box["h"] / 2
        s = min(W / (box["w"] + 2 * pad), H / (box["h"] + 2 * pad), scale_cap)
        s = max(1.0, s)
    hw, hh = W / (2 * s), H / (2 * s)
    cx = min(max(cx, hw), W - hw)
    cy = min(max(cy, hh), H - hh)
    return (cx, cy, s)


def cam_mix(a, b, k):
    return (lerp(a[0], b[0], k), lerp(a[1], b[1], k), math.exp(lerp(math.log(a[2]), math.log(b[2]), k)))


# ------------------------------------------------------------------ segments

class Seg:
    def __init__(self, d: dict):
        self.d, self.id, self.type = d, d["id"], d["type"]
        self.dur = float(d.get("dur", 2.0))
        self.vo_at = float(d.get("vo_at", 0.55))
        self.pcm, self.words, self.caps = None, [], []
        self.start = 0.0

    def wt(self, q, after=-1.0, end=False, default=None):
        """Segment-local time of a narrated word."""
        t = word_time(self.words, q, after - self.vo_at if after >= 0 else -1.0, end)
        return default if t is None else self.vo_at + t

    def vo_len(self):
        return (self.words[-1][0] + self.words[-1][1]) if self.words else 0.0


def lower_third(dst, title, sub, u, t0, dur, bottom=168):
    if u < t0 or u > t0 + dur:
        return
    k_in = prog(u, t0, 0.4, ENTRANCE)
    k_out = 1 - prog(u, t0 + dur - 0.3, 0.3, PRODUCTIVE)
    op = min(k_in, k_out)
    lt = text_layer(title, "IBMPlexSans-SemiBold", 44, TXT)
    ls = text_layer(sub, "IBMPlexSans-Regular", 28, TXT2)
    bw = max(lt.shape[1], ls.shape[1]) + 32 + 40
    bh = 20 + 56 + 40 + 24
    x, y = 96, H - bottom - bh + 16 * (1 - k_in)
    rect(dst, x, y, 8, bh, ACCENT, op)
    rect(dst, x + 8, y, bw, bh, BG, 0.92 * op)
    blit(dst, lt, x + 8 + 32, y + 20, op)
    blit(dst, ls, x + 8 + 32, y + 20 + 58, op)


def draw_caption(dst, text, op):
    lines = wrap(text, "IBMPlexSans-SemiBold", 40, 1500)
    lays = [text_layer(s, "IBMPlexSans-SemiBold", 40, (255, 255, 255)) for s in lines]
    lh = 52
    bw = max(l.shape[1] for l in lays) + 56
    bh = lh * len(lays) + 28
    x, y = (W - bw) / 2, H - 56 - bh
    rect(dst, x, y, bw, bh, (0, 0, 0), 0.72 * op)
    for i, l in enumerate(lays):
        blit(dst, l, (W - l.shape[1]) / 2, y + 12 + i * lh, op)


# ---- hook: the painting, a push-in to one pixel, then back out

def render_hook(seg: Seg, u: float) -> np.ndarray:
    dst = canvas()
    ty, tx = FACTS["truth"]
    before, after = FACTS["pixel_before"], FACTS["pixel_after"]
    ch = FACTS["edit"]["params"]["channel"]
    t_changed = seg.wt("changed", default=3.0)
    t_shade = seg.wt("shade", end=True, default=5.0)
    t_can = seg.wt("Can", default=6.0)
    t_neither = seg.wt("Neither", default=8.0)
    t_quantum = seg.wt("quantum", default=9.5)
    z0 = 880 / 256
    za = z0 * (1 + 0.03 * prog(u, 0, t_changed, PRODUCTIVE))
    k_in = prog(u, t_changed - 0.1, 2.4, EXPRESSIVE)
    k_out = prog(u, t_can + 0.5, 1.9, EXPRESSIVE)
    k = k_in * (1 - k_out)
    z = math.exp(lerp(math.log(za), math.log(56.0), k))
    P = (tx + 0.5, ty + 0.5)
    s0 = (W / 2 + (P[0] - 128) * za, H / 2 + (P[1] - 128) * za)       # where the pixel sits in the full view
    sp = (lerp(s0[0], W / 2, k), lerp(s0[1], H / 2, k))
    cx, cy = P[0] - (sp[0] - W / 2) / z, P[1] - (sp[1] - H / 2) / z
    img = ART.copy()
    edited = u > t_shade - 0.6 and ((u - (t_shade - 0.6)) % 1.2 < 0.6 or u > t_can)
    if edited:
        img[ty, tx] = after
    m = np.float32([[z, 0, W / 2 - cx * z], [0, z, H / 2 - cy * z]])
    soft = cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=BG)
    blend = min(1.0, max(0.0, (z - 6) / 6))
    if blend > 0:
        hard = cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=BG)
        soft = cv2.addWeighted(hard, blend, soft, 1 - blend, 0)
    fade = prog(u, 0, 0.9, PRODUCTIVE)
    dst = dst * (1 - fade) + soft.astype(np.float32) * fade
    # the pixel: highlight + its value
    k_mark = prog(u, t_changed + 1.4, 0.5, ENTRANCE) * (1 - prog(u, t_can + 0.3, 0.4, PRODUCTIVE))
    if k_mark > 0:
        px, py = W / 2 + (tx - cx) * z, H / 2 + (ty - cy) * z
        frame_rect(dst, px - z / 2 - 6, py - z / 2 - 6, z + 12, z + 12, TXT, 3, k_mark)
        val = (after if edited else before)[ch]
        name = "RGB"[ch]
        l1 = text_layer(f"pixel ({ty}, {tx})", "IBMPlexMono-Regular", 30, TXT2)
        l2 = text_layer(f"{name} {val:3d}", "IBMPlexMono-SemiBold", 64, TXT)
        bx, by = px + z / 2 + 56, py - 96
        rect(dst, bx - 32, by - 24, 360, 196, BG, 0.9 * k_mark)
        rect(dst, bx - 32, by - 24, 8, 196, ACCENT, k_mark)
        blit(dst, l1, bx, by, k_mark)
        blit(dst, l2, bx, by + 40, k_mark)
        l3 = text_layer(f"was {before[ch]}: one shade" if edited else "original", "IBMPlexSans-Regular", 26, HELP)
        blit(dst, l3, bx, by + 124, k_mark)
    # "A quantum fingerprint can": the tile's fingerprint lights up
    k_fp = prog(u, t_quantum, 0.6, ENTRANCE)
    if k_fp > 0:
        cxz, cyz, zz = cx, cy, z
        tile_x = W / 2 + (tx // 4 * 4 - cxz) * zz
        tile_y = H / 2 + (ty // 4 * 4 - cyz) * zz
        s = 4 * zz
        pulse = 1 + 0.6 * (1 - prog(u, t_quantum, 0.9, EXPRESSIVE))
        frame_rect(dst, tile_x - (pulse - 1) * s / 2 - 4, tile_y - (pulse - 1) * s / 2 - 4, s * pulse + 8, s * pulse + 8,
                   ALERT, 3, k_fp)
    return dst


# ---- title card with the mosaic motif

def mosaic_tiles(dst, x, y, size, u, t0, t_flip, highlight=None, k_hl=0.0):
    """Artwork tiles resolve in, then a diagonal wave turns each tile into its fingerprint colour."""
    n = 64
    cell = size / n
    art = cv2.resize(ART, (n, n), interpolation=cv2.INTER_AREA).astype(np.float32)
    mos = MOSAIC.astype(np.float32)
    ii, jj = np.mgrid[0:n, 0:n]
    diag = (ii + jj) / (2 * n - 2)
    a_in = np.clip((u - t0 - diag * 0.9) / 0.45, 0, 1)
    a_in = ease_arr(ENTRANCE, a_in)
    f = np.clip((u - t_flip - diag * 1.2) / 0.35, 0, 1)
    col = art * (1 - f[..., None]) + mos * f[..., None]
    big = cv2.resize(col, (int(size), int(size)), interpolation=cv2.INTER_NEAREST)
    al = cv2.resize(a_in.astype(np.float32), (int(size), int(size)), interpolation=cv2.INTER_NEAREST)
    lay = np.dstack([big, al])
    blit(dst, lay, x, y)
    if highlight is not None and k_hl > 0:
        ty, tx = highlight
        frame_rect(dst, x + (tx // 4) * cell - 5, y + (ty // 4) * cell - 5, cell + 10, cell + 10, ALERT, 3, k_hl)


def render_title(seg: Seg, u: float) -> np.ndarray:
    dst = grid_bg().copy()
    d = seg.d
    rise(dst, text_layer(d["kicker"], "IBMPlexSans-Regular", 28, TXT2), 128, 236, u, 0.15, 0.5, ease=ENTRANCE)
    k_bar = prog(u, 0.25, 0.7, EXPRESSIVE)
    if k_bar > 0:
        gradient_bar(dst, 128, 300, 160, 8, 1.0, k_bar)
    rise(dst, text_layer(d["title"], "IBMPlexSans-SemiBold", 168, TXT, track=-2), 120, 352, u, 0.35, 0.7, 24, EXPRESSIVE)
    rise(dst, text_layer(d["sub"], "IBMPlexSans-Regular", 48, TXT2), 128, 580, u, 0.55, 0.7, 20, EXPRESSIVE)
    foot = text_layer("SwapPrint", "IBMPlexSans-SemiBold", 24, TXT)
    rise(dst, foot, 128, 935, u, 0.8, 0.5)
    rise(dst, text_layer("·  team sardines", "IBMPlexSans-Regular", 24, HELP), 128 + foot.shape[1] + 8, 935, u, 0.8, 0.5)
    mosaic_tiles(dst, 1216, 252, 576, u, 0.1, 1.1, FACTS["truth"], prog(u, 2.5, 0.4, ENTRANCE))
    return dst


def render_section(seg: Seg, u: float) -> np.ndarray:
    dst = grid_bg().copy()
    d = seg.d
    num = text_layer(d["num"], "IBMPlexMono-SemiBold", 360, ACCENT, track=-8)
    k = prog(u, 0.0, 0.5, PRODUCTIVE)
    blit(dst, num, 128, H / 2 - num.shape[0] / 2 + 10, 0.95 * k)
    lines = d["title"].split("|")
    y = 400 - 60 * (len(lines) - 1)
    k_bar = prog(u, 0.1, 0.6, EXPRESSIVE)
    if k_bar > 0:
        gradient_bar(dst, 700, y - 48, 160, 8, 1.0, k_bar)
    for i, s in enumerate(lines):
        rise(dst, text_layer(s, "IBMPlexSans-SemiBold", 104, TXT, track=-1), 696, y + i * 116, u, 0.12 + 0.06 * i, 0.5, 20,
             EXPRESSIVE)
    rise(dst, text_layer(d.get("sub", ""), "IBMPlexSans-Regular", 40, TXT2), 700, y + len(lines) * 116 + 28, u, 0.3,
         0.5, 16, EXPRESSIVE)
    return dst


def render_end(seg: Seg, u: float) -> np.ndarray:
    dst = grid_bg().copy()
    d = seg.d
    rise(dst, text_layer("Thank you for watching", "IBMPlexSans-Regular", 28, TXT2), 128, 200, u, 0.1)
    k_bar = prog(u, 0.2, 0.7, EXPRESSIVE)
    if k_bar > 0:
        gradient_bar(dst, 128, 264, 160, 8, 1.0, k_bar)
    a, b = d["title"].split("·") if "·" in d["title"] else (d["title"], "")
    la = text_layer(a.strip(), "IBMPlexSans-SemiBold", 120, TXT, track=-1)
    rise(dst, la, 122, 312, u, 0.3, 0.6, 20, EXPRESSIVE)
    if b:
        dot = text_layer("·", "IBMPlexSans-SemiBold", 120, ACCENT_D)
        rise(dst, dot, 122 + la.shape[1] + 18, 312, u, 0.38, 0.6, 20, EXPRESSIVE)
        rise(dst, text_layer(b.strip(), "IBMPlexSans-Regular", 120, TXT2, track=-1), 122 + la.shape[1] + 18 + dot.shape[1]
             + 18, 312, u, 0.45, 0.6, 20, EXPRESSIVE)
    rise(dst, text_layer(d["sub"], "IBMPlexMono-Regular", 40, ACCENT_D), 128, 500, u, 0.6, 0.5)
    for i, s in enumerate(d.get("lines", [])):
        rise(dst, text_layer(s, "IBMPlexSans-Regular", 34, TXT2), 128, 588 + i * 52, u, 0.75 + 0.08 * i, 0.5)
    credits = [
        "Design tokens: Carbon Design System (Apache-2.0). Typeface: IBM Plex (SIL OFL 1.1). Artwork: Hokusai, "
        "The Great Wave, public domain (The Met).",
        f"{NARRATION_CREDIT} Music: an original pad "
        "generated in code. SwapPrint is an independent project, not made or endorsed by IBM.",
    ]
    credit_lines = [line for credit in credits for line in wrap(credit, "IBMPlexSans-Regular", 22, 1664)]
    for i, s in enumerate(credit_lines):
        rise(dst, text_layer(s, "IBMPlexSans-Regular", 22, HELP), 128, 800 + i * 30, u, 1.0, 0.5)
    return dst


# ---- the idea, as a diagram that builds itself

def render_diagram(seg: Seg, u: float) -> np.ndarray:
    dst = grid_bg().copy()
    ty, tx = FACTS["truth"]
    r0, c0 = ty // 4 * 4, tx // 4 * 4
    t_copy = seg.wt("copied", default=0.8)
    t_sp = seg.wt("SwapPrint", default=3.2)
    t_patch = seg.wt("patch", default=5.0)
    t_q = seg.wt("eleven", default=6.0)
    t_code = seg.wt("error", default=8.0)
    t_buhr = seg.wt("Buhrman", default=9.5)
    t_swap = seg.wt("SWAP", default=12.0)
    t_ident = seg.wt("Identical", default=15.0)
    t_chg = seg.wt("changed", after=t_ident, default=17.0)

    # 1. the artwork, and its copies fanning out
    PX, PY, PS = 128, 150, 400
    art_l = image_layer(ART, PS, PS, cv2.INTER_CUBIC)
    k_copy = prog(u, t_copy, 0.9, EXPRESSIVE) * (1 - prog(u, t_sp - 0.2, 0.7, EXPRESSIVE))
    for i in (3, 2, 1):
        if k_copy > 0:
            blit(dst, art_l, PX + 34 * i * k_copy, PY + 34 * i * k_copy * 0.4, (0.55 / i) * k_copy)
    rise(dst, art_l, PX, PY, u, 0.0, 0.6, 20, EXPRESSIVE)
    # 2. the tile grid and the one tile
    k_grid = prog(u, t_patch - 0.4, 0.8, PRODUCTIVE)
    if k_grid > 0:
        step = PS / 64
        for i in range(1, 64):
            rect(dst, PX + i * step, PY, 1, PS, BG, 0.35 * k_grid)
            rect(dst, PX, PY + i * step, PS, 1, BG, 0.35 * k_grid)
        rise(dst, text_layer("64 × 64 = 4,096 tiles", "IBMPlexSans-Regular", 26, TXT2), PX, PY + PS + 20, u,
             t_patch - 0.2)
    hx, hy, hs = PX + c0 / 256 * PS, PY + r0 / 256 * PS, 4 / 256 * PS
    k_tile = prog(u, t_patch, 0.6, EXPRESSIVE)
    TX, TY, TS = 640, 270, 160
    if k_tile > 0:
        frame_rect(dst, hx - 3, hy - 3, hs + 6, hs + 6, ACCENT_D, 2, k_tile)
        tile = ART[r0:r0 + 4, c0:c0 + 4]
        tl = image_layer(tile, TS, TS, cv2.INTER_NEAREST)
        for p, q in (((hx + hs, hy), (TX, TY)), ((hx + hs, hy + hs), (TX, TY + TS))):
            line(dst, p, (lerp(p[0], q[0], k_tile), lerp(p[1], q[1], k_tile)), BORDER, 2, k_tile)
        blit(dst, tl, TX, TY + 12 * (1 - k_tile), k_tile)
        frame_rect(dst, TX, TY + 12 * (1 - k_tile), TS, TS, ACCENT_D, 2, k_tile)
        rise(dst, text_layer("one 4 × 4 tile", "IBMPlexSans-SemiBold", 26, TXT), TX, TY - 44, u, t_patch + 0.1)
        rise(dst, text_layer("384 bits", "IBMPlexMono-Regular", 24, TXT2), TX, TY + TS + 16, u, t_patch + 0.2)
    # 3. the code: 2,048-bit codeword, filled in scan order
    CX, CY, cell = 900, 270, 5
    k_code = prog(u, t_code, 1.4, PRODUCTIVE)
    if u > t_code - 0.3:
        rise(dst, text_layer("error-correcting code", "IBMPlexSans-SemiBold", 26, TXT), CX, CY - 44, u, t_code - 0.3)
        line(dst, (TX + TS + 16, TY + TS / 2), (lerp(TX + TS + 16, CX - 20, prog(u, t_code - 0.3, 0.5)), TY + TS / 2),
             BORDER, 2)
        bits = codeword_bits("codeword_a")
        nshow = int(2048 * k_code)
        lay = np.zeros((32 * cell, 64 * cell, 4), np.float32)
        b = bits.reshape(32, 64)
        for r in range(32):
            for c in range(64):
                if r * 64 + c >= nshow:
                    break
                col = ACCENT if b[r, c] else LAYER2
                lay[r * cell:(r + 1) * cell - 1, c * cell:(c + 1) * cell - 1, :3] = col
                lay[r * cell:(r + 1) * cell - 1, c * cell:(c + 1) * cell - 1, 3] = 1
        blit(dst, lay, CX, CY)
        rise(dst, text_layer("2,048-bit codeword", "IBMPlexMono-Regular", 24, TXT2), CX, CY + 32 * cell + 16, u,
             t_code + 0.4)
    k_b = prog(u, t_buhr - 0.2, 0.5, ENTRANCE)
    if k_b > 0:
        blit(dst, text_layer("after Buhrman, Cleve, Watrous & de Wolf, PRL 2001", "IBMPlexSans-Regular", 22, HELP),
             CX, CY + 32 * cell + 56, k_b)
    # 4. the 11-qubit state
    SX = 1420
    k_s = prog(u, t_q, 0.6, EXPRESSIVE)
    if k_s > 0:
        line(dst, (CX + 64 * cell + 20, TY + TS / 2), (lerp(CX + 64 * cell + 20, SX - 24, k_s), TY + TS / 2), BORDER, 2)
        ket(dst, SX, 268 + 14 * (1 - k_s), "ψ", 120, TXT, k_s)
        blit(dst, text_layer("11 qubits", "IBMPlexSans-SemiBold", 30, TXT), SX, 440, k_s)
        blit(dst, text_layer("2,048 amplitudes, signs from the code", "IBMPlexSans-Regular", 22, TXT2), SX, 480,
             k_s)
    # 5. the SWAP test circuit, drawn left to right
    if u > t_swap - 0.4:
        y_a, y_p, y_f = 660, 740, 820
        x0, x1 = 420, 1240
        k_w = prog(u, t_swap - 0.4, 1.0, PRODUCTIVE)
        for yy in (y_a, y_p, y_f):
            rect(dst, x0, yy - 1, (x1 - x0) * k_w, 2, TXT2)
        labs = [("ancilla", "0", y_a), ("original", "ψ", y_p), ("under test", "φ", y_f)]
        for name, inner, yy in labs:
            lt = text_layer(name, "IBMPlexSans-Regular", 24, TXT2)
            blit(dst, lt, x0 - 120 - lt.shape[1], yy - 17, k_w)
            ket(dst, x0 - 104, yy - 22, inner, 32, TXT, k_w)

        def gate(x, yy, label, t):
            k = prog(u, t, 0.4, EXPRESSIVE)
            if k > 0:
                rect(dst, x - 26, yy - 26, 52, 52, ACCENT, k)
                lay = text_layer(label, "IBMPlexSans-SemiBold", 30, (255, 255, 255))
                blit(dst, lay, x - lay.shape[1] / 2 + 2, yy - 21, k)
        gate(580, y_a, "H", t_swap + 0.2)
        k_c = prog(u, t_swap + 0.5, 0.5, EXPRESSIVE)
        if k_c > 0:
            ring(dst, 800, y_a, 9, TXT, fill=True, op=k_c)
            rect(dst, 799, y_a, 3, (y_f - y_a) * k_c, TXT)
            for yy in (y_p, y_f):
                line(dst, (788, yy - 12), (812, yy + 12), TXT, 3, k_c)
                line(dst, (788, yy + 12), (812, yy - 12), TXT, 3, k_c)
            blit(dst, text_layer("controlled-SWAP", "IBMPlexSans-Regular", 22, HELP), 740, y_f + 30, k_c)
        gate(1000, y_a, "H", t_swap + 0.8)
        k_m = prog(u, t_swap + 1.1, 0.4, EXPRESSIVE)
        if k_m > 0:
            rect(dst, 1150, y_a - 28, 64, 56, LAYER1, k_m)
            frame_rect(dst, 1150, y_a - 28, 64, 56, TXT2, 2, k_m)
            line(dst, (1182, y_a + 16), (1200, y_a - 14), TXT, 2, k_m)
            m = np.zeros((H, W), np.uint8)
            cv2.ellipse(m, (1182, y_a + 16), (22, 22), 0, 200, 340, 255, 2, cv2.LINE_AA)
            a = (m.astype(np.float32) / 255 * k_m)[..., None]
            dst[:] = dst * (1 - a) + np.array(TXT, np.float32) * a

        # readouts
        def readout(yy, label, vals, t, p1):
            k = prog(u, t, 0.4, ENTRANCE)
            if k <= 0:
                return
            blit(dst, text_layer(label, "IBMPlexSans-SemiBold", 26, TXT), 1290, yy - 46, k)
            for i, v in enumerate(vals):
                kk = prog(u, t + 0.15 + i * 0.12, 0.25, ENTRANCE)
                if kk <= 0:
                    continue
                col = ALERT50 if v else LAYER2
                rect(dst, 1290 + i * 40, yy, 32, 32, col, kk)
                lay = text_layer(str(v), "IBMPlexMono-SemiBold", 20, (255, 255, 255) if v else TXT2)
                blit(dst, lay, 1290 + i * 40 + 10, yy + 3, kk)
            blit(dst, text_layer(p1, "IBMPlexMono-Regular", 24, TXT2), 1290 + len(vals) * 40 + 16, yy + 2, k)
        readout(y_a - 10, "identical tiles", [0] * 8, t_ident, "p1 = 0")
        readout(y_f - 30, "changed tile", [0, 1, 1, 0, 1, 0, 0, 1], t_chg, "p1 ≈ 0.5")
    return dst


# ---- the contrast: 7 shots against 15.5 million, on a log scale

def render_chart(seg: Seg, u: float) -> np.ndarray:
    dst = grid_bg().copy()
    strict, frqi = FACTS["strict_99"], FACTS["frqi_99"]
    rise(dst, text_layer("Shots for 99% detection of this one-pixel edit", "IBMPlexSans-SemiBold", 56, TXT),
         128, 120, u, 0.0, 0.5, 16, EXPRESSIVE)
    rise(dst, text_layer("Same image, same edit, same SWAP test · exact values · log scale", "IBMPlexSans-Regular", 30,
                         TXT2), 128, 200, u, 0.12, 0.5)
    X0, X1 = 640, 1760
    decades = 8

    def xpos(v):
        return X0 + (X1 - X0) * (math.log10(max(v, 1)) / decades)
    k_ax = prog(u, 0.2, 0.8, PRODUCTIVE)
    ticks = ["1", "10", "100", "1k", "10k", "100k", "1M", "10M", "100M"]
    for i, lab in enumerate(ticks):
        x = X0 + (X1 - X0) * i / decades
        rect(dst, x, 340, 1, 470, BORDER, 0.6 * k_ax)
        lay = text_layer(lab, "IBMPlexMono-Regular", 22, HELP)
        blit(dst, lay, x - lay.shape[1] / 2, 822, k_ax)
    rows = [("Pixels as angles", "FRQI, the textbook encoding", frqi, rgb(C["gray-60"]), (255, 255, 255), "angle"),
            ("SwapPrint", "error-correcting code, 11 qubits", strict, ACCENT, (255, 255, 255), "SwapPrint")]
    for i, (name, sub, val, col, tcol, cue) in enumerate(rows):
        y = 400 + i * 200
        t0 = seg.wt(cue, default=1.5 + 3 * i) - 0.1
        rise(dst, text_layer(name, "IBMPlexSans-SemiBold", 40, TXT), 128, y, u, 0.3 + 0.1 * i)
        rise(dst, text_layer(sub, "IBMPlexSans-Regular", 26, TXT2), 128, y + 56, u, 0.4 + 0.1 * i)
        grow = 3.4 if val > 1000 else 0.7
        k = prog(u, t0, grow, EXPRESSIVE)
        if k > 0:
            v = 10 ** (math.log10(val) * k)
            xe = xpos(v)
            rect(dst, X0, y + 4, max(2, xe - X0), 88, col)
            label = f"{v:,.0f}" + (" shots" if k >= 0.999 else "")
            lay = text_layer(label, "IBMPlexMono-SemiBold", 44, TXT)
            lx = xe + 20 if xe + 20 + lay.shape[1] < W - 40 else xe - lay.shape[1] - 20
            blit(dst, lay, lx, y + 20)
    t_end = seg.wt("seven", default=8.0)
    k_r = prog(u, t_end + 0.6, 0.6, ENTRANCE)
    if k_r > 0:
        ratio = frqi / strict
        lay = text_layer(f"{ratio / 1e6:.1f} million times fewer shots, for the same edit", "IBMPlexSans-SemiBold", 40,
                         ACCENT_D)
        blit(dst, lay, 128, 878 + 12 * (1 - k_r), k_r)
    return dst


# ---- rigour: quick cuts of the real figures

@lru_cache(maxsize=16)
def fig_layer(name: str, max_w: int, max_h: int):
    im = np.asarray(Image.open(ROOT / "experiments" / "figures" / name).convert("RGB"))
    h, w = im.shape[:2]
    s = min(max_w / w, max_h / h)
    return image_layer(im, int(w * s), int(h * s), cv2.INTER_AREA)


def render_figures(seg: Seg, u: float) -> np.ndarray:
    cards = seg.d["cards"]
    if not hasattr(seg, "_starts"):
        st, after = [0.0], -1.0
        for i, c in enumerate(cards[1:], 1):
            t = seg.wt(c["cue"], after=after, default=st[-1] + 4.0)
            after = t + 0.01
            st.append(max(st[-1] + 1.0, t - 0.25))
        seg._starts = st
    starts = seg._starts
    i = max(0, bisect.bisect_right(starts, u) - 1)

    def card(j, uu):
        c = cards[j]
        dst = grid_bg().copy()
        rect(dst, 128, 120, 96, 8, ACCENT)
        big = text_layer(c["big"], "IBMPlexSans-SemiBold", 112, TXT, track=-1)
        rise(dst, big, 122, 150, uu, 0.0, 0.35, 12, ENTRANCE)
        rise(dst, text_layer(c["label"], "IBMPlexSans-Regular", 34, TXT2), 128 + big.shape[1] + 36, 214, uu, 0.08, 0.35,
             10)
        fl = fig_layer(c["fig"], 1664, 560)
        s = 1.0 + 0.035 * prog(uu, 0, 4.5, PRODUCTIVE)
        fh, fw = fl.shape[:2]
        lay = cv2.resize(fl, (int(fw * s), int(fh * s)), interpolation=cv2.INTER_LINEAR) if s > 1.001 else fl
        pad = 20
        k = prog(uu, 0.05, 0.4, ENTRANCE)
        rect(dst, 128, 340, fw + 2 * pad, fh + 2 * pad, (255, 255, 255), k)
        # crop the slowly growing figure back into its frame (a gentle push-in)
        oy, ox = (lay.shape[0] - fh) // 2, (lay.shape[1] - fw) // 2
        blit(dst, lay[oy:oy + fh, ox:ox + fw], 128 + pad, 340 + pad, k)
        return dst
    dst = card(i, u - starts[i])
    if i > 0 and u - starts[i] < 0.25:      # quick 250 ms dissolve: confident cuts
        k = PRODUCTIVE((u - starts[i]) / 0.25)
        prev = card(i - 1, u - starts[i - 1])
        dst = prev * (1 - k) + dst * k
    return dst


# ---- the app take

class AppSeg(Seg):
    def plan(self, take: Take):
        self.take = take
        d = self.d
        b = take.beats[self.id]
        self.src0 = take.resolve(self.id, d["clip"]) if d.get("clip") is not None else b["t0"]
        self.src_end = b["t1"]
        self.pre = 0.0                                     # seconds of frozen first frame before playback
        self.sync_hold = None
        self.cuts = []
        if d.get("sync") and self.words:
            sy = d["sync"]
            if str(sy["src"]).startswith("magenta:"):
                self.src0, anchor = self.find_magenta(take, int(sy["src"].split(":")[1]), sy.get("region"))
            else:
                anchor = take.resolve(self.id, sy["src"])
            t_word = self.wt(sy["word"], default=self.vo_at + 1.0)
            want = t_word - sy.get("lead", 0.2)
            self.pre = want - (anchor - self.src0)
            if self.pre < 0:
                self.src0 -= self.pre
                self.pre = 0.0
            if d.get("hold_sync"):
                self.sync_hold = (want, float(d["hold_sync"]), anchor)
        else:
            for a in b["actions"]:                       # cut long waits (Aer, verify) out of the footage
                if a["t_idle"] - a["t_click"] > 2.2 and a["t_click"] >= self.src0:
                    self.cuts.append((a["t_click"] + 0.5, a["t_idle"] - 0.8))
        need = max(float(d.get("min_dur", 2.6)), self.vo_at + self.vo_len() + 0.9)
        self.dur = max(need, 1.0)
        # camera keyframes
        self.keys = []
        for k in d.get("camera", []):
            tgt = k.get("target", "full")
            box = b["targets"].get(tgt) if tgt != "full" else None
            if tgt != "full" and not box:
                continue
            at = k.get("at", 0)
            at = self.src_to_out(take.resolve(self.id, at)) if isinstance(at, str) else float(at)
            focus = FACTS["truth"] if k.get("focus") == "truth" else None
            cam = (960.0, 540.0, 1.0) if tgt == "full" else cam_for_box(box, float(k.get("scale", 1.6)), focus=focus)
            self.keys.append((at, float(k.get("dur", 1.4)), cam))
        self.clicks = [(self.src_to_out(a["t_click"]), a["click"]) for a in b["actions"] if a.get("click")]

    def find_magenta(self, take, n, region):
        """First frame after action n's click with no magenta in the region (the shot strip has restarted), and the
        first later frame where magenta appears (the first 1). Returns their times on the take clock."""
        b = take.beats[self.id]
        t_click = b["actions"][n]["t_click"]
        box = b["targets"].get(region) if region else None
        k = take.dpr
        i0 = max(0, bisect.bisect_right(take.times, t_click) - 1)
        free, first = None, None
        for i in range(i0, min(len(take.times), i0 + 60)):
            if take.times[i] > t_click + 4:
                break
            im = cv2.imread(str(take.files[i]))
            if box:
                im = im[int(box["y"] * k):int((box["y"] + box["h"]) * k), int(box["x"] * k):int((box["x"] + box["w"]) * k)]
            bgr = im.astype(np.int16)
            cnt = int(np.count_nonzero((bgr[..., 2] > 180) & (bgr[..., 1] < 120) & (bgr[..., 0] > 100)))
            if free is None and take.times[i] >= t_click and cnt < 40:
                free = take.times[i]
            elif free is not None and cnt > 150:
                first = take.times[i]
                break
        if free is None or first is None:
            print(f"  {self.id}: magenta sync not found, using the click time")
            return t_click + 0.15, t_click + 0.3
        return free + 0.001, first

    def out_to_src(self, u):
        if self.sync_hold:
            at, duration, source = self.sync_hold
            if at <= u < at + duration:
                return source
            if u >= at + duration:
                u -= duration
        if u < self.pre:
            return self.src0
        t = self.src0 + (u - self.pre)
        for a, z in self.cuts:
            if t >= a:
                t += z - a
        return min(t, self.src_end)

    def src_to_out(self, t):
        u = self.pre + (t - self.src0)
        for a, z in self.cuts:
            if t >= z:
                u -= z - a
        if self.sync_hold and t > self.sync_hold[2]:
            u += self.sync_hold[1]
        return u

    def cam(self, u):
        c = (960.0, 540.0, 1.0)
        for at, dur, tgt in self.keys:
            if u <= at:
                break
            c = cam_mix(c, tgt, prog(u, at, dur, PRODUCTIVE))
        return c

    def render(self, u):
        fid, src = self.take.frame(self.out_to_src(u))
        if self.d.get("isolated_target"):
            box = self.take.beats[self.id]["targets"][self.d["isolated_target"]]
            dpr = self.take.dpr
            x0, y0 = int(box["x"] * dpr), int(box["y"] * dpr)
            art = src[y0:int((box["y"] + box["h"]) * dpr),
                      x0:int((box["x"] + box["w"]) * dpr)]
            ah, aw = art.shape[:2]
            k = prog(u, 1.2, 2.6, PRODUCTIVE)
            zoom = math.exp(lerp(0, math.log(3.2), k))
            ty, tx = FACTS["truth"]
            cw, ch = aw / zoom, ah / zoom
            cx = min(max(lerp(aw / 2, (tx + .5) / 256 * aw, k), cw / 2), aw - cw / 2)
            cy = min(max(lerp(ah / 2, (ty + .5) / 256 * ah, k), ch / 2), ah - ch / 2)
            matrix = np.float32([[cw / 800, 0, cx - cw / 2], [0, ch / 800, cy - ch / 2]])
            focused = cv2.warpAffine(art, matrix, (800, 800),
                                      flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP,
                                      borderMode=cv2.BORDER_REPLICATE)
            dst = grid_bg().copy()
            blit(dst, image_layer(focused, 800, 800), 980, 100)
            frame_rect(dst, 980, 100, 800, 800, BORDER)
            rect(dst, 128, 164, 96, 8, ACCENT)
            blit(dst, text_layer("Located.", "IBMPlexSans-SemiBold", 110, TXT), 122, 218)
            row, col = FACTS["tile_rc"]
            blit(dst, text_layer(f"Tile ({row}, {col})", "IBMPlexMono-Medium", 42, ALERT50), 128, 374)
            blit(dst, text_layer(f"Pixel ({ty}, {tx}) · one shade", "IBMPlexSans-Regular", 30, TXT2), 128, 446)
            blit(dst, text_layer("Recorded app heatmap", "IBMPlexSans-Regular", 26, HELP), 128, 560)
            blit(dst, text_layer("Analytical sampler · noiseless model", "IBMPlexSans-Regular", 26, HELP), 128, 602)
            return dst
        c = self.cam(u)
        dst = render_view(src, fid, c)
        cx, cy, s = c
        for tc, (px, py) in self.clicks:            # click pulse: Carbon purple ring, 500 ms
            if 0 <= u - tc <= 0.6 and 0 <= py <= H:
                k = (u - tc) / 0.6
                ox, oy = (px - cx) * s + W / 2, (py - cy) * s + H / 2
                ring(dst, ox, oy, (16 + 26 * PRODUCTIVE(k)) * s, ACCENT_D, 4, 0.9 * (1 - k))
                ring(dst, ox, oy, 7 * s, ACCENT_D, 3, 0.8 * (1 - k), fill=True)
        lt = self.d.get("lower")
        if lt:
            at = lt["at"]
            at = self.src_to_out(self.take.resolve(self.id, at)) if isinstance(at, str) else float(at)
            lower_third(dst, lt["title"], lt["sub"].format(**fmt_vars()), u, at, float(lt.get("dur", 4.5)))
        return dst


RENDER = {"hook": render_hook, "title": render_title, "section": render_section, "diagram": render_diagram,
          "chart": render_chart, "figures": render_figures, "end": render_end}


# ------------------------------------------------------------------ music: an original, quiet pad (no licence needed)

def pad(dur: float) -> np.ndarray:
    n = int(dur * SR)
    t = np.arange(n) / SR
    chords = [[110.0, 164.81, 220.0, 261.63, 329.63, 493.88],     # A minor add9
              [87.31, 130.81, 220.0, 261.63, 329.63, 392.0],      # F major 7
              [130.81, 196.0, 246.94, 329.63, 392.0, 493.88],     # C major 7
              [98.0, 146.83, 196.0, 246.94, 293.66, 440.0]]       # G add9
    seg_len = 8.0
    out = np.zeros(n, np.float32)
    rng = np.random.default_rng(7)
    for ci in range(int(dur / seg_len) + 2):
        c0 = ci * seg_len - 2.0
        env = np.clip((t - c0) / 3.0, 0, 1) * np.clip((c0 + seg_len + 4.0 - t) / 3.0, 0, 1)
        env = np.sin(env * np.pi / 2) ** 2
        if env.max() == 0:
            continue
        idx = np.nonzero(env)[0]
        for f in chords[ci % 4]:
            ph = rng.uniform(0, 2 * np.pi)
            for det in (-0.6, 0.6):
                ff = f * (1 + det / 1200 * 4)
                vib = 0.002 * np.sin(2 * np.pi * 0.13 * t[idx] + ph)
                out[idx] += (env[idx] * np.sin(2 * np.pi * ff * t[idx] * (1 + vib) + ph) / (1 + f / 220)).astype(np.float32)
    spec = np.fft.rfft(out)                       # gentle low-pass, 12 dB/octave above ~1.2 kHz
    f = np.fft.rfftfreq(n, 1 / SR)
    out = np.fft.irfft(spec / (1 + (f / 1200.0) ** 2), n).astype(np.float32)
    fade = np.clip(t / 2.5, 0, 1) * np.clip((dur - t) / 3.0, 0, 1)
    return out * fade / (np.abs(out).max() + 1e-9)


# ------------------------------------------------------------------ build

def build(args):
    global NARRATION_CREDIT
    manifest_path = getattr(args, "human_manifest", None)
    human = load_json(manifest_path) if manifest_path else None
    NARRATION_CREDIT = (f"Narration: {human['narrator']} (original human recording)." if human else
                        "Narration: none (captions only)." if args.no_tts else
                        f"Narration: synthetic timing reference ({META['voice']}, Microsoft Edge text-to-speech).")
    voice, rate = META["voice"], META.get("rate", "+0%")
    take = Take(TAKE) if TAKE else None
    vars_ = fmt_vars()
    segs = []
    for d in TL["segments"]:
        if d.get("show") is False:
            continue
        s = AppSeg(d) if d["type"] == "app" else Seg(d)
        vo = (d.get("vo") or "").format(**vars_)
        if vo:
            spoken = (d.get("tts") or d["vo"]).format(**vars_)
            if human:
                s.pcm, s.words = human_clip(manifest_path, human["segments"][s.id])
            elif args.no_tts:
                s.pcm, s.words = None, fake_words(spoken)
            else:
                s.pcm, s.words = tts(spoken, voice, rate)
            s.caps = caption_chunks(vo, s.words)
        if d["type"] == "section":
            s.dur = float(d.get("dur", 2.1))
        elif d["type"] in ("diagram", "chart", "figures", "hook", "end"):
            s.dur = max(float(d.get("dur", 0)), s.vo_at + s.vo_len() + (1.0 if d["type"] != "end" else 3.0))
        if isinstance(s, AppSeg):
            s.plan(take)
        segs.append(s)
    t = 0.0
    for s in segs:
        s.start = t
        t += s.dur - XF
    total = t + XF
    captions = []
    for s in segs:
        for a, b, c in s.caps:
            captions.append((s.start + s.vo_at + a, s.start + s.vo_at + b, c))
    print(f"{len(segs)} segments, {total:.1f} s")
    for s in segs:
        print(f"  {s.start:6.1f}  {s.dur:5.1f}  {s.type:8s} {s.id}")
    return segs, captions, total


def frame_at(segs, captions, T) -> np.ndarray:
    act = [s for s in segs if s.start - 1e-6 <= T < s.start + s.dur]
    if not act:
        act = [segs[-1]]
    s = act[-1]
    fn = s.render if isinstance(s, AppSeg) else (lambda u, s=s: RENDER[s.type](s, u))
    img = fn(T - s.start)
    if len(act) > 1:
        p = act[-2]
        k = PRODUCTIVE((T - s.start) / XF)
        pf = p.render if isinstance(p, AppSeg) else (lambda u, p=p: RENDER[p.type](p, u))
        img = pf(T - p.start) * (1 - k) + img * k
    for a, b, c in captions:
        if a <= T < b + 0.2:
            op = min(prog(T, a, 0.15), 1 - prog(T, b, 0.2))
            draw_caption(img, c, op)
    return img


def boxcar_same(values, width):
    """Linear-time equivalent of a centered, zero-padded boxcar convolution."""
    padded = np.pad(values, (width // 2, (width - 1) // 2))
    integral = np.empty(len(padded) + 1, dtype=np.float64)
    integral[0] = 0
    np.cumsum(padded, dtype=np.float64, out=integral[1:])
    return ((integral[width:] - integral[:-width]) / width).astype(np.float32)


def mix_audio(segs, total, music: bool) -> Path:
    n = int((total + 0.5) * SR)
    vo = np.zeros(n, np.float32)
    for s in segs:
        if s.pcm is not None:
            i = int((s.start + s.vo_at) * SR)
            vo[i:i + len(s.pcm)] += s.pcm[:max(0, n - i)]
    mixd = vo
    if music:
        p = pad(n / SR)
        speech = boxcar_same(np.abs(vo), SR // 5) > 0.01
        duck = boxcar_same(speech.astype(np.float32), SR // 2)
        vrms = np.sqrt(np.mean(vo[np.abs(vo) > 0.01] ** 2)) if np.any(np.abs(vo) > 0.01) else 0.1
        level = vrms * 10 ** (-17 / 20) * (1 - 0.45 * duck)   # ~17 dB under the voice, ~22 dB while it speaks
        mixd = vo + p * level * math.sqrt(2)
    raw = OUT / "mix_raw.wav"
    with wave.open(str(raw), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes((np.clip(mixd, -1, 1) * 32767).astype(np.int16).tobytes())
    # two-pass EBU R128 loudness normalisation to -16 LUFS
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = json.loads(r.stderr[r.stderr.rindex("{"):r.stderr.rindex("}") + 1])
    norm_p = OUT / "mix.wav"
    af = (f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af", af, "-ar", str(SR), "-ac", "2",
                    str(norm_p)], check=True)
    return norm_p


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", default="")
    narration = ap.add_mutually_exclusive_group(required=True)
    narration.add_argument("--no-tts", action="store_true", help="Explicit captions-only preview")
    ap.add_argument("--no-music", action="store_true")
    narration.add_argument("--human-manifest", type=Path, help="ingest_narration.py output; required for final voiced export")
    narration.add_argument("--reference-tts", action="store_true", help="Explicitly generate a synthetic timing reference")
    ap.add_argument("--out")
    args = ap.parse_args()
    if not (args.human_manifest or args.reference_tts or args.no_tts):
        ap.error("Final narration must be Rashida's recording: pass --human-manifest. Use --reference-tts only for timing previews.")
    if args.out is None:
        args.out = str(OUT / ("swapprint_demo.mp4" if args.human_manifest else
                              "captions_preview.mp4" if args.no_tts else "reference_tts.mp4"))
    segs, captions, total = build(args)
    if args.stills:
        qc = OUT / "qc"
        qc.mkdir(parents=True, exist_ok=True)
        ts = [float(x) for x in args.stills.split(",")]
        thumbs = []
        for T in ts:
            img = np.clip(frame_at(segs, captions, T), 0, 255).astype(np.uint8)
            Image.fromarray(img).save(qc / f"still_{T:06.2f}.png")
            thumbs.append(Image.fromarray(img).resize((640, 360), Image.LANCZOS))
        cols = 3
        sheet = Image.new("RGB", (640 * cols, 360 * math.ceil(len(thumbs) / cols)))
        for k, im in enumerate(thumbs):
            sheet.paste(im, ((k % cols) * 640, (k // cols) * 360))
        sheet.save(qc / "sheet.png")
        print("wrote", qc / "sheet.png")
        return
    OUT.mkdir(parents=True, exist_ok=True)
    audio = mix_audio(segs, total, META.get("music", True) and not args.no_music)
    silent = OUT / "video_only.mp4"
    nframes = int(round(total * FPS))
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                            "-r", str(FPS), "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                            "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-profile:v", "high",
                            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                            "-color_range", "tv", str(silent)], stdin=subprocess.PIPE)
    for i in range(nframes):
        img = frame_at(segs, captions, i / FPS)
        enc.stdin.write(np.clip(img + 0.5, 0, 255).astype(np.uint8).tobytes())
        if i % 300 == 0:
            print(f"  frame {i}/{nframes}", flush=True)
    enc.stdin.close()
    if enc.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding video frames")
    final = Path(args.out)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(silent), "-i", str(audio), "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1:video_full_range_flag=0",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(final)],
                   check=True)
    srt = final.with_suffix(".srt")
    with open(srt, "w", encoding="utf-8") as f:
        for k, (a, b, c) in enumerate(captions, 1):
            def ts_(x):
                ms = int(round(x * 1000))
                return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
            f.write(f"{k}\n{ts_(a)} --> {ts_(b)}\n{c}\n\n")
    (OUT / "timeline_resolved.json").write_text(json.dumps(
        {"total": total, "segments": [{"id": s.id, "type": s.type, "start": s.start, "dur": s.dur} for s in segs],
         "captions": captions}, indent=1), encoding="utf-8")
    print(f"wrote {final} ({final.stat().st_size / 1e6:.1f} MB, {total:.1f} s) and {srt}")


if __name__ == "__main__":
    main()
