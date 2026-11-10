import unittest

import config
from modules.obstacle_analyzer import (
    ObstacleAnalyzer, get_direction, get_priority, get_proximity, build_message,
)

SIZE = (1280, 720)


def det(label, bbox, conf=0.9):
    return {"label": label, "confidence": conf, "bbox": bbox}


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class TestHelpers(unittest.TestCase):
    def test_direction(self):
        self.assertEqual(get_direction([0, 0, 100, 100], 1280), "left")
        self.assertEqual(get_direction([600, 0, 700, 100], 1280), "centre")
        self.assertEqual(get_direction([1100, 0, 1200, 100], 1280), "right")

    def test_proximity(self):
        self.assertEqual(get_proximity([0, 0, 50, 600], 720), "very close")
        self.assertEqual(get_proximity([0, 0, 50, 300], 720), "near")
        self.assertEqual(get_proximity([0, 0, 50, 100], 720), "far")

    def test_priority(self):
        self.assertEqual(get_priority("person"), "high")
        self.assertEqual(get_priority("chair"), "medium")
        self.assertEqual(get_priority("cup"), "low")

    def test_message(self):
        self.assertEqual(build_message("person", "centre", "very close"), "Person ahead, very close")
        self.assertEqual(build_message("chair", "left", "far"), "Chair on your left")


class TestAnalyzer(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.analyzer = ObstacleAnalyzer(clock=self.clock)

    def feed(self, detections, n):
        result = None
        for _ in range(n):
            result = self.analyzer.analyze(detections, SIZE) or result
        return result

    def test_rank_prefers_person_over_chair(self):
        ranked = self.analyzer.rank([det("chair", [600, 100, 700, 600]),
                                     det("person", [600, 100, 700, 300])], SIZE)
        self.assertEqual(ranked[0]["label"], "person")

    def test_unstable_detection_not_announced(self):
        person = [det("person", [600, 100, 700, 600])]
        self.assertIsNone(self.analyzer.analyze(person, SIZE))
        self.assertIsNone(self.analyzer.analyze([], SIZE))
        self.assertIsNone(self.analyzer.analyze(person, SIZE))

    def test_stable_detection_announced_once(self):
        person = [det("person", [600, 100, 700, 600])]
        decisions = [self.analyzer.analyze(person, SIZE) for _ in range(config.STABLE_WINDOW)]
        announced = [d for d in decisions if d]
        self.assertEqual(len(announced), 1)
        self.assertEqual(announced[0]["direction"], "centre")
        self.assertEqual(announced[0]["priority"], "high")

    def test_repeat_after_cooldown(self):
        person = [det("person", [600, 100, 700, 600])]
        self.assertIsNotNone(self.feed(person, config.STABLE_MIN))
        self.assertIsNone(self.feed(person, 3))
        self.clock.t += config.REPEAT_COOLDOWN_S + 1
        self.assertIsNotNone(self.feed(person, 1))

    def test_closer_obstacle_breaks_cooldown(self):
        far = [det("person", [600, 100, 700, 300])]
        close = [det("person", [500, 50, 800, 700])]
        self.feed(far, config.STABLE_MIN)
        result = self.feed(close, 1)
        self.assertIsNotNone(result)
        self.assertEqual(result["proximity"], "very close")

    def test_empty(self):
        self.assertIsNone(self.analyzer.analyze([], SIZE))


if __name__ == "__main__":
    unittest.main()
