"""The narrated reveal must follow captured outcomes and never reveal a 1 early."""
import unittest
import finish


class RecordedShotStory(unittest.TestCase):
    def test_capture_data_is_required_and_validated(self):
        text = "Play shots\n\n0\n1\n1\n0\nAfter 4 shots: 2 ones"
        self.assertEqual(finish.recorded_shot_sequence(text, 4, 2), (0, 1, 1, 0))
        for args in [(text, 32, 2), (text, 4, 1), ("No captured sample", 4, 2)]:
            with self.assertRaises(ValueError):
                finish.recorded_shot_sequence(*args)

    def test_first_one_waits_for_voice_cue_and_holds_through_shot_two(self):
        trace = (0, 1, 1, 0)
        before = finish.shot_count_at(5.99, 6, 8.5, len(trace))
        reveal = finish.shot_count_at(6, 6, 8.5, len(trace))
        held = finish.shot_count_at(8.49, 6, 8.5, len(trace))
        self.assertEqual(sum(trace[:before]), 0)
        self.assertEqual((reveal, held), (2, 2))
        self.assertEqual(finish.shot_count_at(20, 6, 8.5, len(trace)), 4)
        early = finish.recorded_shot_card(trace, before, 51, 39, .499969)
        later = finish.recorded_shot_card(trace, reveal, 51, 39, .499969)
        self.assertNotEqual(tuple(early[400, 346]), finish.ALERT50)
        self.assertEqual(tuple(later[400, 346]), finish.ALERT50)


if __name__ == "__main__":
    unittest.main()
