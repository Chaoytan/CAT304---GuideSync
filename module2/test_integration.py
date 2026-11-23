"""Exercise the proposed Module 1 interface without YOLO or a physical camera."""
from dataclasses import dataclass
from types import SimpleNamespace
import unittest
from .direction_checkpoint import Route, process_frame


@dataclass
class Detection:
    frame_id: int = 7
    timestamp: float = 1.25
    class_name: str = "chair"
    confidence: float = .91
    box_xyxy: tuple = (500, 100, 600, 300)
    zone: str = "right"


class TestInterface(unittest.TestCase):
    def setUp(self):
        self.frame = SimpleNamespace(shape=(1080, 1920, 3))
        self.route = Route()

    def read(self, frame):
        self.assertIs(frame, self.frame)
        return [10]

    def run_frame(self, *items, **kwargs):
        return process_frame(self.frame, items, 7, 1.25, self, self.route, **kwargs)

    def test_right_side_from_resized_detector(self):
        event = self.run_frame(Detection())
        self.assertEqual(event["objects"][0]["text"], "chair, right of view.")
        self.assertEqual(event["checkpoint"]["status"], "expected_visible")

    def test_edge_overrun_and_invalid_boxes(self):
        boxes = [(600,10,640.4,100), (700,5,705,10), (float("nan"),1,50,50)]
        event = self.run_frame(*(Detection(box_xyxy=b) for b in boxes))
        self.assertEqual([o["bbox"] for o in event["objects"]], [[600,10,640,100]])
        self.assertEqual(event["checkpoint"]["seen"], [10])

    def test_empty_or_stale_detections_still_read_markers(self):
        for items in [[], [Detection(frame_id=6)]]:
            event = self.run_frame(*items)
            self.assertEqual(event["objects"], [])
            self.assertEqual(event["checkpoint"]["status"], "expected_visible")

    def test_explicit_size_and_legacy_input(self):
        box = (500,100,600,300)
        actual = self.run_frame(Detection(box_xyxy=box), detector_size=(1280,720))
        self.assertEqual(actual["objects"][0]["position"], "centre")
        legacy = self.run_frame({"label": "chair", "bbox": box})
        self.assertEqual(legacy["objects"][0]["position"], "left")
