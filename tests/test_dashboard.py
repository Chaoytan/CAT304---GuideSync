import unittest

import numpy as np

from ui.dashboard import draw


class TestDashboard(unittest.TestCase):
    def test_draw_returns_new_frame_with_same_shape(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        detections = [{"label": "person", "confidence": 0.91, "bbox": [500, 120, 780, 700]}]
        decision = {"message": "Person ahead, very close", "priority": "high"}

        out = draw(frame, detections, decision=decision, fps=30.0, latency_ms=12.0, muted=False)
        self.assertEqual(out.shape, frame.shape)
        self.assertIsNot(out, frame)
        self.assertEqual(int(frame.sum()), 0)
        self.assertGreater(int(out.sum()), 0)


if __name__ == "__main__":
    unittest.main()
