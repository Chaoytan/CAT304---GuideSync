"""GuideSync Module 2. One Route per session; never opens a camera or plays audio."""
import json
from pathlib import Path


def locate_objects(width, height, detections):
    """Accept filtered Module 1 detections; xyxy must be original-frame pixels."""
    if width <= 0 or height <= 0:
        raise ValueError("Invalid frame dimensions")
    objects = []
    for item in detections:
        x1, y1, x2, y2 = item["bbox"]
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            raise ValueError("Invalid box; expected original-frame xyxy pixel coordinates")
        centre = (x1 + x2) / 2
        side = "left" if centre < width / 3 else "centre" if centre < 2 * width / 3 else "right"
        objects.append({**item, "position": side, "text": f"{item['label']}, {side} of view."})
    return objects


class Route:
    def __init__(self, path=None):
        path = Path(path) if path else Path(__file__).with_name("route.json")
        self.steps = json.loads(path.read_text(encoding="utf8"))
        self.ids = [step["id"] for step in self.steps]
        if not self.ids or len(set(self.ids)) != len(self.ids):
            raise ValueError("Use a nonempty route with unique marker IDs")
        self.reset()

    def reset(self):
        self.index = 0
        self.pending = None

    def observe(self, ids):
        """Report a candidate cue only for a single expected marker."""
        seen = sorted(set(int(i) for i in ids))
        self.pending = None
        expected = self.ids[self.index] if self.index < len(self.ids) else None
        result = {"seen": seen, "expected": expected, "text": None}
        if expected is None:
            status = "complete"
        elif not seen:
            status = "not_visible"
        elif len(seen) != 1:
            status = "ambiguous"
        elif seen[0] not in self.ids:
            status = "unknown"
        elif seen[0] in self.ids[:self.index]:
            status = "already_confirmed"
        elif seen[0] != expected:
            status = "out_of_order"
        else:
            step = self.steps[self.index]
            self.pending = expected
            status = "expected_visible"
            result.update(name=step["name"], text=step["cue"], duplicate_key=f"checkpoint:{expected}")
        return {**result, "status": status}

    def confirm(self, marker_id):
        """Operator confirms at this checkpoint while its marker is still visible."""
        if self.pending is None or marker_id != self.pending:
            return False
        self.index += 1
        self.pending = None
        return True


class MarkerReader:
    def __init__(self):
        import cv2
        self.cv = cv2
        a = cv2.aruco
        self.detector = a.ArucoDetector(a.getPredefinedDictionary(a.DICT_4X4_50), a.DetectorParameters())

    def read(self, frame):
        gray = self.cv.cvtColor(frame, self.cv.COLOR_BGR2GRAY)
        _, ids, _ = self.detector.detectMarkers(gray)
        return [] if ids is None else ids.flatten().tolist()


def process_frame(frame, detections, frame_id, captured_at, reader, route):
    """Call once per matched fresh frame; keep reader and route between calls."""
    h, w = frame.shape[:2]
    return {"frame_id": frame_id, "captured_at": captured_at,
            "objects": locate_objects(w, h, detections),
            "checkpoint": route.observe(reader.read(frame))}
