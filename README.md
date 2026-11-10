# CAT304 - GuideSync
CAT304 Project - An AI-Assisted Navigation System for People with Visual Impairments

Pipeline: camera -> object detection (YOLO) -> obstacle analysis (left/centre/right, proximity, priority) -> spoken guidance.

## Setup
```
python -m venv venv
.\venv\Scripts\Activate.ps1      
python -m pip install -r requirements.txt
```

## Run
```
set CAM_INDEX=1              (find yours with: python scripts\find_cam.py)
python main.py               # full pipeline, live camera
python main.py --source demo.mp4 --no-voice   # video file, print instead of speak
python main.py --mock --no-voice              # no YOLO needed
```
Keys in the preview window: `q` quit, `m` mute/unmute voice. Each run writes a CSV (FPS, latency, message) to `logs/`.

Camera test scripts (all read `CAM_INDEX`): `scripts/find_cam.py`, `scripts/preview.py`, `scripts/fps_test.py`, `scripts/marker_test.py`.

## Tests
```
python -m unittest discover -s tests -t .
```

## Project layout and owners
| Path | Owner | Purpose |
|---|---|---|
| `modules/camera.py`, `modules/detection.py` | Member 1 | Frame capture; YOLO detection (`MockDetector` for offline work) |
| `modules/obstacle_analyzer.py` | Member 2 | Direction, proximity heuristic, priority, stability and repeat filtering |
| `modules/voice_guidance.py` | Member 3 | Non-blocking text-to-speech, rate limiting, mute |
| `main.py`, `ui/dashboard.py`, `tests/`, `config.py` | Member 4 | Integration, preview overlay, logging, tests |

## Shared interfaces
Detection: `{"label": "person", "confidence": 0.91, "bbox": [x1, y1, x2, y2]}` (pixels).
Decision: `{"message": "Person ahead, very close", "direction": "centre", "priority": "high", "label": "person", "proximity": "very close"}`.

Use feature branches: `feature/camera`, `feature/obstacle-logic`, `feature/voice`.

## Notes
- Tested on Windows, Python 3.12
- Distance is estimated from bounding-box height only; a single camera cannot measure real distance, so treat it as experimental.
- Model weights (`*.pt`) are git-ignored; ultralytics downloads `yolov8n.pt` on first run. Images and other weights are in the shared Drive folder (link)
