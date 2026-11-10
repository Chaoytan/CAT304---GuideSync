"""Member 1 - object detection.

Interface (agreed with the team):
    detect(frame) -> list of {"label": str, "confidence": float, "bbox": [x1, y1, x2, y2]}
bbox is in pixels: top-left and bottom-right corners.
"""
import config


class YoloDetector:
    """Pretrained YOLO via Ultralytics. The model is loaded lazily on first use."""

    def __init__(self, model_path=None, conf=None):
        self.model_path = model_path or config.MODEL_PATH
        self.conf = conf if conf is not None else config.CONF_THRESHOLD
        self._model = None

    def _load(self):
        from ultralytics import YOLO  # imported here so other modules/tests don't need it
        self._model = YOLO(self.model_path)

    def detect(self, frame):
        if self._model is None:
            self._load()
        result = self._model(frame, conf=self.conf, verbose=False)[0]
        names = result.names
        detections = []
        for box in result.boxes:
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            detections.append({
                "label": names[int(box.cls[0])],
                "confidence": round(float(box.conf[0]), 3),
                "bbox": [x1, y1, x2, y2],
            })
        return detections


class MockDetector:
    """Returns a fixed list of detections. Lets everyone else work without YOLO or a camera."""

    def __init__(self, detections=None):
        self.detections = detections if detections is not None else [
            {"label": "person", "confidence": 0.91, "bbox": [500, 120, 780, 700]},
            {"label": "chair", "confidence": 0.87, "bbox": [900, 400, 1150, 700]},
        ]

    def detect(self, frame):
        return [dict(d) for d in self.detections]
