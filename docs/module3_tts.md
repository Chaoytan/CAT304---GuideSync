# GuideSync – Text-to-Speech module (Module 3)

Offline speech output for the GuideSync prototype (proposal §5.2). It accepts **any**
input style from earlier modules, decides what is worth saying, and speaks it through
`pyttsx3` (Windows SAPI5) with `VoiceGuidance` in `modules/voice_guidance.py` integrating
it into `main.py`.

```
 anything ──► adapters ──► Message ──► SpeechManager ──► SpeechEngine ──► earphones
 (str, dict,   (normalise)  (one      (priority, cooldown,  (pyttsx3 /
  detections,               type)      staleness, queue,     console / fake)
  markers...)                          pause, user requests)
```

## 1. Prerequisites (Windows)

- Python 3.9+ (3.10–3.12 recommended)
- `pyttsx3`, `pywin32`, `comtypes` (included in root `requirements.txt`)
- An English Windows voice (e.g. Microsoft David / Zira)

No camera, YOLO or OpenCV is needed to test this module. No internet is needed after install.

## 2. How to test it (do these in order)

From the repository root:

```powershell
# 1. Logic tests, no audio needed
.\venv\Scripts\python.exe -m unittest discover -s tests -t . -v

# 2. Logic demo with no audio (prints what would be spoken)
.\venv\Scripts\python.exe -m modules.tts --engine console

# 3. REAL VOICE check
.\venv\Scripts\python.exe -m modules.tts
tts> /check
```

At the `tts>` prompt:
- `hello there` — speaks plain text
- `/det chair 0.9 left` — `"Chair, left of view."`
- `/spam chair 20` then `/stats` — repeat suppression stats
- `/marker 1 Junction A | The planned route continues left.` — route cue
- `/marker unknown` — `"Unrecognised marker."`
- `/sys camera_lost` — interrupts routine speech and says the failure notice
- `/repeat`, `/summary` — bypass cooldown and jump the queue
- `/pause`, `/resume` — pause/resume routine announcements
- `/log run1.csv` — export event log (with latency)

Extra options: `--rate 160 --volume 0.9 --voice zira --cooldown 5 --object-ttl 2 --no-suppression`.

**Baseline vs. suppression comparison**:
```powershell
.\venv\Scripts\python.exe -m scripts.tts_replay sample_data/tts_sequence.jsonl
```

## 3. Pipeline & programmatic usage
- `modules/voice_guidance.py` wraps `SpeechManager` in `VoiceGuidance`, used directly by `main.py` (with `--route basic` / `--route lounge` forwarding Module 2 cues as `KIND_ROUTE` `HIGH`-priority speech, `v` repeat, `s` summary, `m` mute/pause).
- Direct usage:
```python
from modules.tts import create_manager, SpeechConfig, AdapterOptions

tts = create_manager("pyttsx3", rate=160, voice="zira")
tts.submit("Hello")
tts.submit({"label": "chair", "confidence": 0.9, "bbox": [100, 50, 300, 400], "frame_width": 640})
tts.submit({"type": "marker", "marker_id": 1, "name": "Junction A", "route_text": "The planned route continues left."})
tts.submit({"type": "system", "event": "camera_lost"})
tts.close()
```

## 4. Files
```
modules/tts/message.py    Message + Priority
modules/tts/adapters.py   any input -> Messages (includes ObstacleAnalyzer & Module 2 event dicts)
modules/tts/engine.py     Pyttsx3Engine (own thread, interruptible), ConsoleEngine, FakeEngine
modules/tts/manager.py    SpeechManager (rules, queue, log, stats)
modules/tts/__main__.py   interactive demo
modules/voice_guidance.py VoiceGuidance facade used by main.py
scripts/tts_replay.py     baseline vs suppression comparison
sample_data/tts_sequence.jsonl
tests/test_tts_adapters.py, tests/test_tts_manager.py, tests/test_tts_engine.py
```
