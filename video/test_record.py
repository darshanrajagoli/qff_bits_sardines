"""Recorder regression: CSS zoom must not shift an image click outside its frame."""
import unittest
from unittest.mock import Mock

from record import do_action


class ImageClickTests(unittest.TestCase):
    def test_zoomed_image_uses_viewport_frame_and_same_click_marker(self):
        page = Mock()
        frame = page.locator.return_value
        frame.bounding_box.return_value = {
            "x": 100, "y": 200, "width": 256, "height": 256,
        }
        # The nested box is 25% too large under the app's 80% desktop zoom.
        image = page.frame_locator.return_value.locator.return_value
        image.bounding_box.return_value = {
            "x": 100, "y": 200, "width": 320, "height": 320,
        }
        marker = do_action(page, {"action": "click_image", "x": .25, "y": .75})
        self.assertEqual(marker, [164, 392])
        page.mouse.click.assert_called_once_with(164, 392)
        image.click.assert_not_called()
        image.bounding_box.assert_not_called()

    def test_missing_frame_aborts_instead_of_recording_a_missed_click(self):
        page = Mock()
        page.locator.return_value.bounding_box.return_value = None
        with self.assertRaisesRegex(RuntimeError, "no viewport box"):
            do_action(page, {"action": "click_image", "x": .25, "y": .75})
        page.mouse.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
