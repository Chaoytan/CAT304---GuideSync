"""Member 1 - camera input.

Wraps cv2.VideoCapture. `source` may be a camera index (int) or a path to a
video file, so the rest of the pipeline can be developed without the camera.
Settings mirror what worked in scripts/preview.py (MSMF backend + MJPG).
"""
import sys

import cv2

import config


class Camera:
    def __init__(self, source=None, width=None, height=None, fps=None):
        self.source = config.CAM_INDEX if source is None else source
        self.width = width or config.FRAME_WIDTH
        self.height = height or config.FRAME_HEIGHT
        self.fps = fps or config.FRAME_FPS
        self.cap = None

    def open(self):
        if isinstance(self.source, int):
            backend = cv2.CAP_MSMF if sys.platform.startswith("win") else cv2.CAP_ANY
            self.cap = cv2.VideoCapture(self.source, backend)
            # FOURCC first: MJPG is needed for high FPS on most USB cameras.
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        else:
            self.cap = cv2.VideoCapture(str(self.source))
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video source: {self.source!r}")
        return self

    def read(self):
        """Return the next BGR frame, or None if the stream ended / was lost."""
        if self.cap is None:
            raise RuntimeError("Camera not opened; call open() first")
        ok, frame = self.cap.read()
        return frame if ok else None

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.release()
