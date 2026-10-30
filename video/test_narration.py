"""Offline signal/timing checks; no voice recording or model download required."""
from pathlib import Path
import tempfile
import unittest

import numpy as np
from ingest_narration import SR, align_script, detect_ranges, read_wav, write_wav


class NarrationChecks(unittest.TestCase):
    def test_four_second_markers_separate_speech_without_cutting_it(self):
        t = np.arange(SR)/SR
        speech = (.15*np.sin(2*np.pi*220*t)*32767).astype(np.int16)
        silence = np.zeros(4*SR, np.int16)
        data = np.concatenate([silence, speech, silence, speech, silence, speech, silence])
        spans, _ = detect_ranges(data)
        self.assertEqual(len(spans), 3)
        for span, onset in zip(spans, (4,9,14)):
            self.assertLessEqual(span[0], onset)
            self.assertGreaterEqual(span[1], onset+1)
            self.assertLess(span[1]-span[0], 1.5)

    def test_number_expansion_does_not_shift_reveal_cue(self):
        recognized = [[i*.4,.25,w] for i,w in enumerate(
            "four thousand shots and there it is on shot two".split())]
        words, score = align_script("4,000 shots and there it is on shot two", recognized)
        self.assertGreater(score, .7)
        actual = next(w[0] for w in recognized if w[2] == "there")
        aligned = next(w[0] for w in words if w[2] == "there")
        self.assertEqual(actual, aligned)

    def test_pcm_is_preserved_by_clip_storage(self):
        out = Path(__file__).resolve().parent/"out"
        out.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out) as tmp:
            path = Path(tmp)/"clip.wav"
            self.assertTrue(path.resolve().is_relative_to(out.resolve()))
            original = np.arange(-1000,1000,dtype=np.int16)
            write_wav(path, original)
            np.testing.assert_array_equal(read_wav(path), original)


if __name__ == "__main__":
    unittest.main()
