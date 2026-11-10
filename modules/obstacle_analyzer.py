"""Member 2 - obstacle analysis and decision logic.

Interface:
    ObstacleAnalyzer.analyze(detections, frame_size) -> decision dict or None
    decision = {"message": "Person ahead, very close", "direction": "centre",
                "priority": "high", "label": "person", "proximity": "very close"}

Proximity is a heuristic from bounding-box height; a single camera cannot
measure real distance, so treat it as experimental.
"""
import time
from collections import deque

import config

PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
PROXIMITY_RANK = {"far": 0, "near": 1, "very close": 2}


def get_direction(bbox, frame_width):
    """Left / centre / right from the horizontal centre of the box."""
    cx = (bbox[0] + bbox[2]) / 2 / frame_width
    if cx < config.LEFT_BOUNDARY:
        return "left"
    if cx > config.RIGHT_BOUNDARY:
        return "right"
    return "centre"


def get_proximity(bbox, frame_height):
    """Rough proximity from how much of the frame height the box fills."""
    frac = (bbox[3] - bbox[1]) / frame_height
    if frac >= config.VERY_CLOSE_HEIGHT_FRAC:
        return "very close"
    if frac >= config.NEAR_HEIGHT_FRAC:
        return "near"
    return "far"


def get_priority(label):
    if label in config.HIGH_PRIORITY_LABELS:
        return "high"
    if label in config.MEDIUM_PRIORITY_LABELS:
        return "medium"
    return "low"


def build_message(label, direction, proximity):
    where = "ahead" if direction == "centre" else f"on your {direction}"
    text = f"{label.capitalize()} {where}"
    if proximity == "very close":
        text += ", very close"
    elif proximity == "near":
        text += ", near"
    return text


def make_decision(det, frame_size):
    width, height = frame_size
    direction = get_direction(det["bbox"], width)
    proximity = get_proximity(det["bbox"], height)
    return {
        "message": build_message(det["label"], direction, proximity),
        "direction": direction,
        "priority": get_priority(det["label"]),
        "label": det["label"],
        "proximity": proximity,
    }


def _score(decision):
    return (
        PRIORITY_RANK[decision["priority"]],
        PROXIMITY_RANK[decision["proximity"]],
        decision["direction"] == "centre",
    )


class ObstacleAnalyzer:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._history = deque(maxlen=config.STABLE_WINDOW)
        self._last_spoken = {}  # (label, direction) -> (time, proximity rank)

    def rank(self, detections, frame_size):
        """All detections as decisions, most important first (no filtering)."""
        decisions = [make_decision(d, frame_size) for d in detections]
        return sorted(decisions, key=_score, reverse=True)

    def analyze(self, detections, frame_size):
        """Return the one decision worth announcing now, or None.

        Filters flickering detections (must be stable over recent frames)
        and suppresses repeats unless the obstacle got closer.
        """
        ranked = self.rank(detections, frame_size)
        self._history.append({(d["label"], d["direction"]) for d in ranked})

        now = self._clock()
        for decision in ranked:
            key = (decision["label"], decision["direction"])
            seen = sum(1 for frame_keys in self._history if key in frame_keys)
            if seen < config.STABLE_MIN:
                continue
            prox = PROXIMITY_RANK[decision["proximity"]]
            last = self._last_spoken.get(key)
            if last is not None:
                last_time, last_prox = last
                if now - last_time < config.REPEAT_COOLDOWN_S and prox <= last_prox:
                    continue
            self._last_spoken[key] = (now, prox)
            return decision
        return None
