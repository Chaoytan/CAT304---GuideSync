import unittest

from modules.direction_checkpoint import Route, locate_objects


class TestDirectionCheckpoint(unittest.TestCase):
    def test_positions_and_boundaries(self):
        for x, side in [(30, "left"), (100, "centre"), (190, "centre"), (200, "right")]:
            result = locate_objects(300, 100, [{"label": "chair", "bbox": [x - 5, 0, x + 5, 50]}])
            self.assertEqual(result[0]["position"], side)

    def test_invalid_and_empty_boxes(self):
        self.assertEqual(locate_objects(640, 480, []), [])
        self.assertEqual(locate_objects(640, 480, [{"label": "chair", "bbox": [800, 0, 820, 40]}]), [])

    def test_no_accidental_progress(self):
        route = Route()
        for ids, status in [
            ([20], "out_of_order"),
            ([49], "unknown"),
            ([10, 20], "ambiguous"),
            ([], "not_visible"),
        ]:
            self.assertEqual(route.observe(ids)["status"], status)
            self.assertFalse(route.confirm(10))

        route.observe([10])
        route.observe([])
        self.assertFalse(route.confirm(10))

    def test_route(self):
        route = Route()
        for marker_id in (10, 20, 30):
            event = route.observe([marker_id])
            self.assertTrue(event["text"])
            self.assertEqual(event, route.observe([marker_id]))
            self.assertTrue(route.confirm(marker_id))
            self.assertFalse(route.confirm(marker_id))

        self.assertEqual(route.observe([30])["status"], "complete")
        route.reset()
        self.assertEqual(route.observe([10])["status"], "expected_visible")


if __name__ == "__main__":
    unittest.main()
