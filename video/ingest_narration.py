"""Split Rashida's phone recording and timestamp her real words locally.

    video/.venv/Scripts/python.exe video/ingest_narration.py take1.m4a
    video/.venv/Scripts/python.exe video/finish.py --human-manifest video/out/human/narration.json

Four-second pauses delimit the frozen script's eleven sections. If a retake or
room noise makes detection ambiguous, edit out/human/detected_ranges.json and
rerun with --ranges that-file.json. Never request a new recording merely to
repair automatic alignment. ASR is local faster-whisper (MIT); it timestamps
the original audio, not generated or cloned speech.
API: https://github.com/SYSTRAN/faster-whisper#word-level-timestamps
"""
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import subprocess
import wave

import numpy as np

HERE = Path(__file__).resolve().parent
SR = 48000


def read_wav(path):
    with wave.open(str(path)) as f:
        if (f.getframerate(), f.getnchannels(), f.getsampwidth()) != (SR, 1, 2):
            raise ValueError("expected 48 kHz mono 16-bit WAV")
        return np.frombuffer(f.readframes(f.getnframes()), np.int16)


def write_wav(path, data):
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data.astype(np.int16).tobytes())


def detect_ranges(data, gap=2.5):
    if not len(data):
        raise ValueError("recording is empty")
    hop = 960  # 20 ms
    padded = np.pad(data, (0, (-len(data)) % hop)).astype(np.float32) / 32768
    rms = np.sqrt(np.mean(padded.reshape(-1, hop) ** 2, axis=1))
    db = 20 * np.log10(rms + 1e-9)
    threshold = np.clip(np.percentile(db, 20) + 12, -55, -32)
    quiet = db < threshold
    changes = np.diff(np.r_[False, quiet, False].astype(int))
    gaps = [(a * .02, b * .02) for a, b in zip(np.where(changes == 1)[0],
                np.where(changes == -1)[0]) if (b-a) * .02 >= gap]
    duration = len(data) / SR
    pieces, start = [], 0.0
    for a, b in gaps + [(duration, duration)]:
        if a - start > .25:
            voiced = np.where((np.arange(len(db)) * .02 >= start) &
                              (np.arange(len(db)) * .02 <= a) & ~quiet)[0]
            if len(voiced):
                pieces.append([max(start, voiced[0] * .02 - .12),
                               min(a, (voiced[-1]+1) * .02 + .18)])
        start = b
    return pieces, float(threshold)


def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def align_script(spoken, recognized):
    if not recognized:
        raise ValueError("no recognized speech to align")
    expected = spoken.split()
    matcher = SequenceMatcher(None, [norm(w) for w in expected],
                              [norm(w[2]) for w in recognized], autojunk=False)
    aligned, equal = [], 0
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            equal += a1-a0
        if a0 == a1:
            continue
        if tag == "equal":
            aligned.extend([[recognized[b0+i][0], recognized[b0+i][1], expected[a0+i]]
                            for i in range(a1-a0)])
        else:
            left = recognized[b0][0] if b0 < len(recognized) else sum(recognized[-1][:2])
            right = sum(recognized[b1-1][:2]) if b1 > b0 else left + .08*(a1-a0)
            step = max(.02, (right-left)/(a1-a0))
            aligned.extend([[left+i*step, step, expected[a0+i]] for i in range(a1-a0)])
    return aligned, equal / max(len(expected), 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path)
    ap.add_argument("--out", type=Path, default=HERE/"out/human")
    ap.add_argument("--ranges", type=Path)
    ap.add_argument("--gap", type=float, default=2.5)
    ap.add_argument("--model", default="tiny.en")
    ap.add_argument("--allow-low-match", action="store_true", help="Only after manually checking the transcript")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    source = out/"source.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(args.input.resolve()),
                    "-ac", "1", "-ar", str(SR), str(source)], check=True)
    data = read_wav(source)
    # Read an override before writing detection output: the user may have edited
    # detected_ranges.json itself, as the recovery instructions recommend.
    override = json.loads(args.ranges.read_text(encoding="utf-8")) if args.ranges else None
    ranges, threshold = detect_ranges(data, args.gap)
    if not args.ranges or args.ranges.resolve() != (out/"detected_ranges.json").resolve():
        (out/"detected_ranges.json").write_text(json.dumps(ranges, indent=2), encoding="utf-8")
    if override is not None:
        ranges = override
    timeline = json.loads((HERE/"timeline.json").read_text(encoding="utf-8"))
    sections = [s for s in timeline["segments"] if s.get("vo") and s.get("show") is not False]
    print(f"Detected {len(ranges)} sections; expected {len(sections)}; silence threshold {threshold:.1f} dBFS", flush=True)
    if len(ranges) != len(sections):
        raise ValueError("Review detected_ranges.json and pass --ranges; preserve the recording")
    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8", cpu_threads=4,
                         download_root=str(HERE/"out/models"))
    manifest = dict(narrator="Rashida Baldiwala", source=str(args.input.resolve()),
                    editorial_approval="pending", segments={})
    problems = []
    for i, (section, bounds) in enumerate(zip(sections, ranges, strict=True), 1):
        a, b = bounds
        if not 0 <= a < b <= len(data)/SR + .01:
            raise ValueError(f"invalid range for {section['id']}")
        clip = out/f"{i:02d}_{section['id']}.wav"
        write_wav(clip, data[int(a*SR):int(b*SR)])
        segments, _ = model.transcribe(str(clip), language="en", word_timestamps=True,
                        beam_size=5, vad_filter=False,
                        initial_prompt="SwapPrint, Qiskit, Hokusai, Marrakesh, SWAP test, SHA-256.")
        actual = [[w.start, max(.02, w.end-w.start), w.word.strip()]
                  for seg in segments for w in (seg.words or [])]
        if not actual:
            raise ValueError(f"no recognized speech in {section['id']}; review this clip")
        spoken = section.get("tts", section["vo"]).format(strict_first_shot=2, strict_first_shot_word="two")
        spoken = spoken.replace("SHA-two-fifty-six", "S H A two fifty-six").replace("...", " ")
        words, match = align_script(spoken, actual)
        manifest["segments"][section["id"]] = dict(audio=clip.name, words=words,
            recognized=" ".join(w[2] for w in actual), match=match, source_range=[a,b])
        print(f"{section['id']}: {b-a:.2f}s, script match {match:.0%}", flush=True)
        if match < .55:
            problems.append(section["id"])
    path = out/"narration_review.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if problems and not args.allow_low_match:
        raise ValueError(f"Check transcript/word timing for {problems}; review saved to {path}")
    (out/"narration.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Ready for human-voice preview:", out/"narration.json", flush=True)


if __name__ == "__main__":
    main()
