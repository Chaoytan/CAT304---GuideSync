"""Module 2 direction and checkpoint logic. One Route per session; never opens a camera or plays audio."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from math import isfinite
from pathlib import Path
from typing import Any, Protocol

DEFAULT_ROUTE_PATH = Path(__file__).resolve().parent / "routes" / "route.json"


class Detection(Protocol):
    """Fields supplied by the Module 1 detector."""

    frame_id: int
    timestamp: float
    class_name: str
    confidence: float
    box_xyxy: tuple[float, float, float, float]
    zone: str


def locate_objects(width: int, height: int, detections: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Clip boxes in their own coordinate system and omit unusable detections."""
    if width <= 0 or height <= 0:
        raise ValueError("Invalid box coordinate dimensions")

    objects: list[dict[str, Any]] = []
    for item in detections:
        try:
            label = item["label"]
            coords = tuple(float(v) for v in item["bbox"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

        if len(coords) != 4 or not all(map(isfinite, coords)) or not isinstance(label, str) or not label.strip():
            continue

        x1, y1, x2, y2 = coords
        x1, y1 = max(0.0, x1), max(0.0, y1)
        x2, y2 = min(float(width), x2), min(float(height), y2)
        if x1 >= x2 or y1 >= y2:
            continue

        centre = (x1 + x2) / 2
        if centre < width / 3:
            side = "left"
        elif centre < 2 * width / 3:
            side = "centre"
        else:
            side = "right"

        objects.append({
            **item,
            "bbox": [x1, y1, x2, y2],
            "position": side,
            "text": f"{label}, {side} of view.",
        })
    return objects


class Route:
    """Ordered checkpoint state machine for ArUco-based navigation."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Load the ordered checkpoint definitions for this session."""
        route_path = Path(path) if path else DEFAULT_ROUTE_PATH
        self.steps: list[dict[str, Any]] = json.loads(route_path.read_text(encoding="utf-8"))
        self.ids: list[int] = [step["id"] for step in self.steps]
        if not self.ids or len(set(self.ids)) != len(self.ids):
            raise ValueError("Use a nonempty route with unique marker IDs")
        self.reset()

    def reset(self) -> None:
        """Start again at the first checkpoint with nothing awaiting confirmation."""
        self.index = 0
        self.pending: int | None = None

    def observe(self, ids: Iterable[int]) -> dict[str, Any]:
        """Report a candidate cue only for a single expected marker."""
        seen = sorted({int(i) for i in ids})
        self.pending = None
        expected = self.ids[self.index] if self.index < len(self.ids) else None
        result: dict[str, Any] = {"seen": seen, "expected": expected, "text": None}

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
            result["name"] = step["name"]
            result["text"] = step["cue"]
            result["duplicate_key"] = f"checkpoint:{expected}"

        return {**result, "status": status}

    def confirm(self, marker_id: int | None) -> bool:
        """Operator confirms at this checkpoint while its marker is still visible."""
        if self.pending is None or marker_id != self.pending:
            return False
        self.index += 1
        self.pending = None
        return True


class MarkerReader:
    """OpenCV ArUco marker detector wrapper."""

    def __init__(self, dictionary_name: str = "DICT_4X4_50") -> None:
        """Create the OpenCV detector for the team marker dictionary."""
        import cv2

        self.cv = cv2
        aruco = cv2.aruco
        dictionary = aruco.getPredefinedDictionary(getattr(aruco, dictionary_name))
        self.detector = aruco.ArucoDetector(dictionary, aruco.DetectorParameters())

    def read(self, frame: Any) -> list[int]:
        """Return marker IDs from an unannotated BGR camera frame."""
        gray = self.cv.cvtColor(frame, self.cv.COLOR_BGR2GRAY)
        _, ids, _ = self.detector.detectMarkers(gray)
        return [] if ids is None else ids.flatten().tolist()


def process_frame(
    frame: Any,
    detections: Iterable[Detection | Mapping[str, Any]],
    frame_id: int,
    captured_at: float,
    reader: MarkerReader,
    route: Route,
    *,
    detector_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    """Read markers at full resolution and classify boxes in detector coordinates.

    Module 1 objects default to the proposed 640 x 360 detector size. Legacy
    label/bbox dictionaries default to camera coordinates. Pass (width, height)
    explicitly when using another size. Only simple whole-frame resizing is assumed.
    """
    h, w = frame.shape[:2]
    checkpoint = route.observe(reader.read(frame))
    objects: list[dict[str, Any]] = []

    for item in detections:
        if isinstance(item, Mapping):
            if item.get("frame_id", frame_id) != frame_id:
                continue
            record: dict[str, Any] = dict(item)
            size = detector_size or (w, h)
        else:
            if item.frame_id != frame_id:
                continue
            record = {
                "label": item.class_name,
                "bbox": item.box_xyxy,
                "confidence": item.confidence,
                "frame_id": item.frame_id,
                "timestamp": item.timestamp,
            }
            size = detector_size or (640, 360)

        for obj in locate_objects(*size, [record]):
            obj["bbox_size"] = size
            objects.append(obj)

    return {
        "frame_id": frame_id,
        "captured_at": captured_at,
        "objects": objects,
        "checkpoint": checkpoint,
    }
