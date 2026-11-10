"""Central settings for GuideSync. Override with environment variables where noted."""
import os

# --- Camera -----------------------------------------------------------------
# Find your index with: python scripts/find_cam.py   then   set CAM_INDEX=1
CAM_INDEX = int(os.environ.get("CAM_INDEX", "0"))
FRAME_WIDTH = int(os.environ.get("FRAME_WIDTH", "1280"))
FRAME_HEIGHT = int(os.environ.get("FRAME_HEIGHT", "720"))
FRAME_FPS = 30

# --- Detection --------------------------------------------------------------
MODEL_PATH = os.environ.get("MODEL_PATH", "yolov8n.pt")  # downloaded by ultralytics on first run
CONF_THRESHOLD = 0.45
DETECT_EVERY_N_FRAMES = 1  # raise to 2-3 on a slow laptop

# --- Obstacle analysis ------------------------------------------------------
# Direction: frame is split into left / centre / right thirds by bbox centre.
LEFT_BOUNDARY = 1 / 3
RIGHT_BOUNDARY = 2 / 3

# Proximity heuristic (single camera, so this is only an estimate):
# based on how much of the frame height the bounding box fills.
VERY_CLOSE_HEIGHT_FRAC = 0.65
NEAR_HEIGHT_FRAC = 0.35

HIGH_PRIORITY_LABELS = {
    "person", "bicycle", "car", "motorcycle", "bus", "truck", "train",
}
MEDIUM_PRIORITY_LABELS = {
    "chair", "couch", "bench", "dining table", "potted plant", "bed",
    "fire hydrant", "stop sign", "traffic light", "suitcase", "backpack",
}

# Stability filter: a (label, direction) must appear in STABLE_MIN of the
# last STABLE_WINDOW analysed frames before it can be announced.
STABLE_WINDOW = 5
STABLE_MIN = 3

# Do not repeat the same alert within this many seconds unless it got closer.
REPEAT_COOLDOWN_S = 4.0

# --- Voice ------------------------------------------------------------------
SPEECH_RATE = 175
MIN_GAP_BETWEEN_SPEECH_S = 1.0

# --- Logging ----------------------------------------------------------------
LOG_DIR = "logs"
