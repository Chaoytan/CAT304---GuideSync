import json
import unittest

from modules.tts import (
    AdapterOptions,
    KIND_OBJECT,
    KIND_ROUTE,
    Message,
    Priority,
    UnsupportedInputError,
    clear_custom_adapters,
    normalize,
    register_adapter,
)


def texts(raw, opts=None):
    return [m.text for m in normalize(raw, opts)]


class TestTtsAdapters(unittest.TestCase):
    def test_plain_string(self):
        (m,) = normalize("  Hello there ")
        self.assertEqual(m.text, "Hello there")
        self.assertEqual(m.priority, Priority.NORMAL)

    def test_empty_string_gives_nothing(self):
        self.assertEqual(normalize("   "), [])
        self.assertEqual(normalize(None), [])

    def test_message_passthrough(self):
        msg = Message("x", priority=Priority.HIGH)
        self.assertIs(normalize(msg)[0], msg)

    def test_text_dict_with_options(self):
        (m,) = normalize({"text": "Hi", "priority": "high", "key": "k", "ttl": 3, "interrupt": True})
        self.assertEqual((m.priority, m.key, m.ttl, m.interrupt), (Priority.HIGH, "k", 3.0, True))

    def test_json_string_is_parsed(self):
        (m,) = normalize(json.dumps({"text": "From JSON", "priority": 4}))
        self.assertEqual(m.text, "From JSON")
        self.assertEqual(m.priority, Priority.USER_REQUEST)

    def test_detection_dict_position(self):
        def det(x):
            return {"label": "chair", "confidence": 0.9, "bbox": [x - 10, 0, x + 10, 50], "frame_width": 600}

        self.assertEqual(texts(det(100)), ["Chair, left of view."])
        self.assertEqual(texts(det(300)), ["Chair, centre of view."])
        self.assertEqual(texts(det(500)), ["Chair, right of view."])

    def test_detection_without_box_has_no_position(self):
        self.assertEqual(texts({"label": "bottle", "confidence": 0.7}), ["Bottle in view."])

    def test_normalised_box_without_width(self):
        self.assertEqual(texts({"label": "chair", "score": 0.9, "box": [0.7, 0.1, 0.9, 0.5]}), ["Chair, right of view."])

    def test_detections_grouped_and_pluralised(self):
        dets = [
            {"label": "person", "confidence": 0.9, "bbox": [10, 0, 50, 50], "frame_width": 600},
            {"label": "person", "confidence": 0.8, "bbox": [20, 0, 60, 50], "frame_width": 600},
            {"label": "chair", "confidence": 0.8, "bbox": [20, 0, 60, 50], "frame_width": 600},
        ]
        self.assertEqual(texts(dets), ["Two people, left of view.", "Chair, left of view."])

    def test_mixed_positions_drop_position(self):
        dets = [
            {"label": "chair", "confidence": 0.9, "bbox": [10, 0, 50, 50], "frame_width": 600},
            {"label": "chair", "confidence": 0.9, "bbox": [500, 0, 560, 50], "frame_width": 600},
        ]
        self.assertEqual(texts(dets), ["Two chairs in view."])

    def test_min_confidence_and_label_filter(self):
        dets = [
            {"label": "chair", "confidence": 0.3},
            {"label": "cat", "confidence": 0.99},
            {"label": "bottle", "confidence": 0.9},
        ]
        opts = AdapterOptions(min_confidence=0.5, labels=["chair", "bottle"])
        self.assertEqual(texts(dets, opts), ["Bottle in view."])

    def test_label_priority_override(self):
        opts = AdapterOptions(label_priorities={"person": "HIGH"})
        (m,) = normalize({"label": "person", "confidence": 0.9}, opts)
        self.assertEqual(m.priority, Priority.HIGH)

    def test_object_key_ignores_position_by_default(self):
        a = normalize({"label": "chair", "confidence": 0.9, "bbox": [0, 0, 20, 5], "frame_width": 600})[0]
        b = normalize({"label": "chair", "confidence": 0.9, "bbox": [580, 0, 600, 5], "frame_width": 600})[0]
        self.assertEqual(a.effective_key, b.effective_key)

    def test_marker_ok(self):
        (m,) = normalize({
            "type": "marker",
            "marker_id": 1,
            "name": "Junction A",
            "route_text": "The planned route continues left.",
        })
        self.assertEqual(m.text, "Junction A identified. The planned route continues left.")
        self.assertEqual(m.priority, Priority.HIGH)
        self.assertEqual(m.kind, "route")

    def test_marker_id_only_and_unknown_and_oos(self):
        self.assertEqual(texts({"marker_id": 7}), ["Marker 7 identified."])
        self.assertEqual(texts({"type": "marker", "status": "unknown"}), ["Unrecognised marker."])
        (m,) = normalize({"type": "marker", "marker_id": 2, "name": "B", "status": "out_of_sequence"})
        self.assertIn("not the expected next checkpoint", m.text)

    def test_system_event(self):
        (m,) = normalize({"type": "system", "event": "camera_lost"})
        self.assertEqual(m.priority, Priority.CRITICAL)
        self.assertIn("Camera disconnected", m.text)
        (m2,) = normalize({"type": "error", "event": "weird_thing"})
        self.assertEqual(m2.text, "System notice: weird thing.")
        self.assertEqual(m2.priority, Priority.CRITICAL)

    def test_obstacle_analyzer_decision_integration(self):
        near = {
            "message": "Person ahead, near",
            "direction": "centre",
            "priority": "high",
            "label": "person",
            "proximity": "near",
        }
        close = {
            "message": "Person ahead, very close",
            "direction": "centre",
            "priority": "high",
            "label": "person",
            "proximity": "very close",
        }
        (m_near,) = normalize(near)
        (m_close,) = normalize(close)
        self.assertEqual(m_near.kind, KIND_OBJECT)
        self.assertEqual(m_near.priority, Priority.HIGH)
        self.assertNotEqual(m_near.effective_key, m_close.effective_key)

    def test_module2_checkpoint_event_integration(self):
        event = {
            "seen": [10],
            "expected": 10,
            "text": "Entrance marker identified. This is the start of the demonstration route.",
            "name": "Entrance",
            "duplicate_key": "checkpoint:10",
            "status": "expected_visible",
        }
        (m,) = normalize(event)
        self.assertEqual(m.kind, KIND_ROUTE)
        self.assertEqual(m.priority, Priority.HIGH)
        self.assertEqual(m.effective_key, "checkpoint:10")

    def test_attribute_objects(self):
        class Det:
            label = "bottle"
            confidence = 0.8
            bbox = (0, 0, 10, 10)
            frame_width = 100

        class Said:
            text = "Attr text"
            priority = "low"

        self.assertEqual(texts(Det()), ["Bottle, left of view."])
        (m,) = normalize(Said())
        self.assertEqual(m.text, "Attr text")
        self.assertEqual(m.priority, Priority.LOW)

    def test_ultralytics_like_result(self):
        class T(list):
            def tolist(self):
                return list(self)

        class Boxes:
            cls = T([56.0, 0.0])
            conf = T([0.9, 0.8])
            xyxy = T([[10, 10, 50, 50], [500, 0, 600, 90]])

        class Results:
            boxes = Boxes()
            names = {0: "person", 56: "chair"}
            orig_shape = (480, 640)

        self.assertEqual(texts(Results()), ["Chair, left of view.", "Person, right of view."])

    def test_generator_input(self):
        self.assertEqual(texts(x for x in ["a", "b"]), ["a", "b"])

    def test_unsupported(self):
        for bad in ({"foo": 1}, 42, object()):
            with self.subTest(bad=bad):
                with self.assertRaises(UnsupportedInputError):
                    normalize(bad)

    def test_custom_adapter(self):
        class Weird:
            pass

        register_adapter(lambda r: isinstance(r, Weird), lambda r, o: "custom works")
        try:
            self.assertEqual(texts(Weird()), ["custom works"])
        finally:
            clear_custom_adapters()

    def test_priority_parse(self):
        self.assertEqual(Priority.parse("user request"), Priority.USER_REQUEST)
        self.assertEqual(Priority.parse(5), Priority.CRITICAL)
        with self.assertRaises(ValueError):
            Priority.parse("nonsense")
        with self.assertRaises(ValueError):
            Priority.parse(99)


if __name__ == "__main__":
    unittest.main()
