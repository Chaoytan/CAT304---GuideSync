"""Live preview overlay (OpenCV window, no extra dependencies)."""
import cv2

import config
from modules.obstacle_analyzer import get_priority

PRIORITY_COLOURS = {  # BGR
    "high": (0, 0, 255),
    "medium": (0, 165, 255),
    "low": (0, 200, 0),
}


def draw(frame, detections, decision=None, fps=0.0, latency_ms=0.0, muted=False, checkpoint=None):
    """Draw boxes, left/centre/right guides, checkpoint status and a status bar."""
    out = frame.copy()
    h, w = out.shape[:2]

    for x in (int(w * config.LEFT_BOUNDARY), int(w * config.RIGHT_BOUNDARY)):
        cv2.line(out, (x, 0), (x, h), (255, 255, 255), 1)

    for d in detections:
        x1, y1, x2, y2 = d["bbox"]
        colour = PRIORITY_COLOURS.get(get_priority(d["label"]), (255, 255, 255))
        cv2.rectangle(out, (x1, y1), (x2, y2), colour, 2)
        cv2.putText(
            out,
            f'{d["label"]} {d["confidence"]:.2f}',
            (x1, max(y1 - 8, 18)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            colour,
            2,
        )

    status = f"FPS {fps:.1f} | latency {latency_ms:.0f} ms | voice {'OFF' if muted else 'ON'}"
    if checkpoint:
        status += f" | route {checkpoint.get('status', '')}"
    cv2.rectangle(out, (0, 0), (w, 34), (0, 0, 0), -1)
    cv2.putText(out, status, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

    banner = None
    banner_colour = (255, 255, 255)
    if checkpoint and checkpoint.get("text"):
        banner = checkpoint["text"]
        banner_colour = (0, 220, 255)
    elif decision:
        banner = decision["message"]
        banner_colour = PRIORITY_COLOURS.get(decision["priority"], (255, 255, 255))

    if banner:
        cv2.rectangle(out, (0, h - 40), (w, h), (0, 0, 0), -1)
        cv2.putText(out, banner, (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.85, banner_colour, 2)

    return out
