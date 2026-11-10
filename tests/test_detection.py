import unittest

import numpy as np

from modules.detection import MockDetector


class TestMockDetector(unittest.TestCase):
    def test_format(self):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        dets = MockDetector().detect(frame)
        self.assertTrue(dets)
        for d in dets:
            self.assertEqual(set(d), {"label", "confidence", "bbox"})
            self.assertEqual(len(d["bbox"]), 4)
            x1, y1, x2, y2 = d["bbox"]
            self.assertTrue(x1 < x2 and y1 < y2)
            self.assertTrue(0 <= d["confidence"] <= 1)


if __name__ == "__main__":
    unittest.main()
