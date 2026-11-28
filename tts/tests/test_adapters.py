import json

import pytest

from guidesync_tts import (AdapterOptions, Message, Priority, UnsupportedInputError,
                           clear_custom_adapters, normalize, register_adapter)


def texts(raw, opts=None):
    return [m.text for m in normalize(raw, opts)]


def test_plain_string():
    (m,) = normalize("  Hello there ")
    assert m.text == "Hello there" and m.priority == Priority.NORMAL


def test_empty_string_gives_nothing():
    assert normalize("   ") == []
    assert normalize(None) == []


def test_message_passthrough():
    msg = Message("x", priority=Priority.HIGH)
    assert normalize(msg)[0] is msg


def test_text_dict_with_options():
    (m,) = normalize({"text": "Hi", "priority": "high", "key": "k", "ttl": 3, "interrupt": True})
    assert (m.priority, m.key, m.ttl, m.interrupt) == (Priority.HIGH, "k", 3.0, True)


def test_json_string_is_parsed():
    (m,) = normalize(json.dumps({"text": "From JSON", "priority": 4}))
    assert m.text == "From JSON" and m.priority == Priority.USER_REQUEST


def test_detection_dict_position():
    d = lambda x: {"label": "chair", "confidence": 0.9, "bbox": [x - 10, 0, x + 10, 50], "frame_width": 600}
    assert texts(d(100)) == ["Chair, left of view."]
    assert texts(d(300)) == ["Chair, centre of view."]
    assert texts(d(500)) == ["Chair, right of view."]


def test_detection_without_box_has_no_position():
    assert texts({"label": "bottle", "confidence": 0.7}) == ["Bottle in view."]


def test_normalised_box_without_width():
    assert texts({"label": "chair", "score": 0.9, "box": [0.7, 0.1, 0.9, 0.5]}) == ["Chair, right of view."]


def test_detections_grouped_and_pluralised():
    dets = [{"label": "person", "confidence": 0.9, "bbox": [10, 0, 50, 50], "frame_width": 600},
            {"label": "person", "confidence": 0.8, "bbox": [20, 0, 60, 50], "frame_width": 600},
            {"label": "chair", "confidence": 0.8, "bbox": [20, 0, 60, 50], "frame_width": 600}]
    assert texts(dets) == ["Two people, left of view.", "Chair, left of view."]


def test_mixed_positions_drop_position():
    dets = [{"label": "chair", "confidence": 0.9, "bbox": [10, 0, 50, 50], "frame_width": 600},
            {"label": "chair", "confidence": 0.9, "bbox": [500, 0, 560, 50], "frame_width": 600}]
    assert texts(dets) == ["Two chairs in view."]


def test_min_confidence_and_label_filter():
    dets = [{"label": "chair", "confidence": 0.3}, {"label": "cat", "confidence": 0.99},
            {"label": "bottle", "confidence": 0.9}]
    opts = AdapterOptions(min_confidence=0.5, labels=["chair", "bottle"])
    assert texts(dets, opts) == ["Bottle in view."]


def test_label_priority_override():
    opts = AdapterOptions(label_priorities={"person": "HIGH"})
    (m,) = normalize({"label": "person", "confidence": 0.9}, opts)
    assert m.priority == Priority.HIGH


def test_object_key_ignores_position_by_default():
    a = normalize({"label": "chair", "confidence": 0.9, "bbox": [0, 0, 20, 5], "frame_width": 600})[0]
    b = normalize({"label": "chair", "confidence": 0.9, "bbox": [580, 0, 600, 5], "frame_width": 600})[0]
    assert a.effective_key == b.effective_key


def test_marker_ok():
    (m,) = normalize({"type": "marker", "marker_id": 1, "name": "Junction A",
                      "route_text": "The planned route continues left."})
    assert m.text == "Junction A identified. The planned route continues left."
    assert m.priority == Priority.HIGH and m.kind == "route"


def test_marker_id_only_and_unknown_and_oos():
    assert texts({"marker_id": 7}) == ["Marker 7 identified."]
    assert texts({"type": "marker", "status": "unknown"}) == ["Unrecognised marker."]
    (m,) = normalize({"type": "marker", "marker_id": 2, "name": "B", "status": "out_of_sequence"})
    assert "not the expected next checkpoint" in m.text


def test_system_event():
    (m,) = normalize({"type": "system", "event": "camera_lost"})
    assert m.priority == Priority.CRITICAL and "Camera disconnected" in m.text
    (m2,) = normalize({"type": "error", "event": "weird_thing"})
    assert m2.text == "System notice: weird thing." and m2.priority == Priority.CRITICAL


def test_attribute_objects():
    class Det:
        label = "bottle"
        confidence = 0.8
        bbox = (0, 0, 10, 10)
        frame_width = 100

    class Said:
        text = "Attr text"
        priority = "low"

    assert texts(Det()) == ["Bottle, left of view."]
    (m,) = normalize(Said())
    assert m.text == "Attr text" and m.priority == Priority.LOW


def test_ultralytics_like_result():
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

    assert texts(Results()) == ["Chair, left of view.", "Person, right of view."]


def test_generator_input():
    assert texts(x for x in ["a", "b"]) == ["a", "b"]


@pytest.mark.parametrize("bad", [{"foo": 1}, 42, object()])
def test_unsupported(bad):
    with pytest.raises(UnsupportedInputError):
        normalize(bad)


def test_custom_adapter():
    class Weird:
        pass

    register_adapter(lambda r: isinstance(r, Weird), lambda r, o: "custom works")
    try:
        assert texts(Weird()) == ["custom works"]
    finally:
        clear_custom_adapters()


def test_priority_parse():
    assert Priority.parse("user request") == Priority.USER_REQUEST
    assert Priority.parse(5) == Priority.CRITICAL
    with pytest.raises(ValueError):
        Priority.parse("nonsense")
    with pytest.raises(ValueError):
        Priority.parse(99)
