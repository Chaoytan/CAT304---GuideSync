# CAT304 - GuideSync
CAT304 Project - An AI-Assisted Navigation System for People with Visual Impairments.

Pipeline: camera -> object detection (YOLO) -> obstacle analysis (left/centre/right, proximity, priority) -> spoken guidance, plus optional ArUco checkpoint/route guidance.

## Setup
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run
```powershell
set CAM_INDEX=1                               # find yours with: python scripts\find_cam.py
python main.py                                # full obstacle pipeline, live camera
python main.py --source demo.mp4 --no-voice   # video file, print instead of speak
python main.py --mock --no-voice              # no YOLO needed

python -m scripts.checkpoint_demo             # Module 2 sample route (no camera/YOLO)
python -m scripts.checkpoint_demo --lounge    # Module 2 branching lounge route sample
```
Keys in the preview window: `q` quit, `m` mute/unmute voice. Each `main.py` run writes a CSV (`time`, `fps`, `latency_ms`, `n_detections`, `message`) to `logs/`.

Camera test scripts (read `CAM_INDEX`): `scripts/find_cam.py`, `scripts/preview.py`, `scripts/fps_test.py`, `scripts/marker_test.py`, `scripts/checkpoint_demo.py`.

## Tests
```powershell
python -m unittest discover -s tests -t . -v
```

## Project layout
| Path | Purpose |
|---|---|
| `modules/camera.py`, `modules/detection.py` | Frame capture; YOLO detection (`MockDetector` for offline work) |
| `modules/obstacle_analyzer.py` | Direction, proximity heuristic, priority, stability and repeat filtering |
| `modules/voice_guidance.py` | Non-blocking text-to-speech, rate limiting, mute |
| `modules/direction_checkpoint.py`, `modules/lounge.py` | ArUco checkpoint reader, linear & branching route state machines |
| `modules/routes/route.json`, `modules/routes/lounge.json` | Checkpoint and lounge route cue configurations |
| `main.py`, `ui/dashboard.py`, `config.py` | Pipeline integration, preview overlay, logging, central config |
| `scripts/` | Camera diagnostics and standalone checkpoint demo |
| `tests/` | Unit and integration tests for all modules and UI |
| `docs/module2_checkpoint.md` | Module 2 checkpoint setup, desk testing, and integration notes |

## Shared interfaces
- Detection: `{"label": "person", "confidence": 0.91, "bbox": [x1, y1, x2, y2]}` (pixels).
- Decision: `{"message": "Person ahead, very close", "direction": "centre", "priority": "high", "label": "person", "proximity": "very close"}`.

## Notes
- Tested on Windows, Python 3.12.
- Distance is estimated from bounding-box height only; a single camera cannot measure real distance, so treat it as experimental.
- Model weights (`*.pt`) are git-ignored; `ultralytics` downloads `yolov8n.pt` on first run.
