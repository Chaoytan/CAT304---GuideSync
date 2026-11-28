# GuideSync – Text-to-Speech module

Offline speech output for the GuideSync prototype (proposal §5.2). It accepts **any**
input style from earlier modules, decides what is worth saying, and speaks it through
pyttsx3 (Windows SAPI5).

```
 anything ──► adapters ──► Message ──► SpeechManager ──► SpeechEngine ──► earphones
 (str, dict,   (normalise)  (one      (priority, cooldown,  (pyttsx3 /
  detections,               type)      staleness, queue,     console / fake)
  markers...)                          pause, user requests)
```

## 1. Prerequisites (Windows)

| Need | How |
|---|---|
| Python 3.9+ (3.10–3.12 recommended) | https://www.python.org/downloads/ – tick "Add Python to PATH" |
| pyttsx3 | `pip install pyttsx3` |
| pywin32 / comtypes (only if you get `No module named 'win32com'`) | `pip install pywin32 comtypes` |
| pytest (for the tests) | `pip install pytest` |
| An English voice | Windows ships "Microsoft David/Zira". Check: Settings → Time & Language → Speech |
| Earphones plugged in and set as the default output device | Sound settings |

No camera, YOLO or OpenCV is needed to test this module. No internet is needed after install.

## 2. How to test it (do these in order)

From the folder that contains `guidesync_tts/` (this README's folder):

```
pip install -r requirements.txt

:: 1. Logic tests, no audio needed (should print "68 passed")
python -m pytest -q

:: 2. Logic demo with no audio (prints what would be spoken)
python -m guidesync_tts --engine console

:: 3. REAL VOICE – the important one on your laptop
python -m guidesync_tts
tts> /check
```

`/check` lists the installed voices and says a test sentence – this is your start-up
sound check from §5.1. If you hear it, the engine works. Then try, at the `tts>` prompt:

| Type this | Expect |
|---|---|
| `hello there` | speaks plain text |
| `/det chair 0.9 left` | "Chair, left of view." |
| `/spam chair 20` then `/stats` | spoken **once**; `dropped` shows cooldown/duplicate counts (repeat suppression) |
| `/det person 0.9 centre` then `/det person 0.9 centre` | second one silent for 5 s |
| `/marker 1 Junction A \| The planned route continues left.` | "Junction A identified. The planned route continues left." |
| `/marker unknown` | "Unrecognised marker." |
| `/sys camera_lost` | cuts off any routine speech, says the failure notice (§5.4 failure response) |
| `/repeat`, `/summary` | user requests: bypass cooldown, jump the queue |
| `/pause`, then `/det chair 0.9 left` | silent; `/resume` restores |
| `/json {"text": "Hi", "priority": "high"}` | any dict/JSON the adapters understand |
| `/log run1.csv` | exports the event log (latency etc.) for your evaluation report |

Extra options: `--rate 170 --volume 0.9 --voice zira --cooldown 5 --object-ttl 2 --no-suppression`.

**Baseline vs. suppression comparison** (proposal §5.3, "same recorded sequence"):
`python replay.py sample_sequence.jsonl` – prints announcement counts without and with
suppression. Replace the file with your own recorded sequence later (one JSON per line:
`{"t": seconds, "input": ...}`).

**Latency note:** the log's `latency_s` is *event created → engine reports speech started*.
The proposal wants audible onset measured externally (phone recording / observer), so use
the log as a cross-check, not as the final number.

## 3. Using it from the other modules

```python
from guidesync_tts import create_manager, SpeechConfig, AdapterOptions

tts = create_manager("pyttsx3", rate=170)          # "console" / "fake" for no audio

tts.submit("Hello")                                 # plain text
tts.submit({"text": "Battery low", "priority": "HIGH"})
tts.submit({"label": "chair", "confidence": 0.9,    # a detection
            "bbox": [100, 50, 300, 400], "frame_width": 640})
tts.submit(yolo_results[0])                         # raw Ultralytics Results works too
tts.submit([det1, det2, det3])                      # lists are grouped: "Two people, left of view."
tts.submit({"type": "marker", "marker_id": 1,       # ArUco checkpoint
            "name": "Junction A", "route_text": "The planned route continues left."})
tts.submit({"type": "system", "event": "camera_lost"})
tts.cancel_pending(["object"])                      # call when the camera dies
tts.repeat_last(); tts.request_summary()            # keyboard controls
tts.toggle_pause()
print(tts.stats()); tts.export_log("log.csv")
tts.close()
```

Pass `created_at=<time.monotonic() of the camera frame>` to `submit` so staleness and latency
are measured from the frame, not from when the message arrived.

### Supported inputs
`str` · JSON string · `Message` · dict with `text`/`message` · detection dict or object
(`label|class_name|name`, `confidence|conf|score`, `zone|position`, `bbox|box|xyxy|box_xyxy`,
`timestamp`, optional `frame_width`) · marker dict (`type: "marker"` or `marker_id`;
`status: ok|unknown|out_of_sequence`) · system dict (`type: "system"`, `event`) · objects with
those attributes · Ultralytics `Results` · lists/generators of any of these. Anything else raises
`UnsupportedInputError`; teach it a new type with `register_adapter(predicate, func)`.

### Input from the Object Detection module
The detector's `Detection` records are read **by field name** (duck typing), so this module never
imports the detector:

| Detector field | How it is used |
|---|---|
| `class_name` | the spoken label ("Dining table") |
| `zone` (`left` / `centre` / `right`) | the spoken position. **It wins over the box.** `center` and any letter case are accepted. An invalid zone (e.g. `middle`) is ignored. |
| `box_xyxy` | fallback only, when there is no valid zone. Needs the frame width (`AdapterOptions(frame_width=640)`), otherwise the message says "in view". |
| `timestamp` (`time.monotonic()` of the camera frame) | becomes `Message.created_at`, so staleness (2 s) and the logged latency are measured from the **frame**, not from when the message arrived. For a group, the earliest timestamp is used. An explicit `submit(..., created_at=...)` always wins. |
| `confidence`, `frame_id` | not spoken. The detector has already applied thresholds. |

Because the detector already applies the per-class thresholds and the five-class whitelist
(`src/config.py`), keep `AdapterOptions.min_confidence` and `labels` at `None` for detector input,
so there is one source of truth. (`check_output.py` sets them only to test filtering.)

How the Integration module calls it:

```python
for tick in pipeline:                        # or FakeDetector(...).run()
    if tick.camera_status == "lost":
        tts.cancel_pending(["object"])
        tts.submit({"type": "system", "event": "camera_lost"})
    elif tick.detections:
        tts.submit(tick.detections)          # created_at comes from the detections
```

### Tunable values (`SpeechConfig`, all to be recorded in your report)
`cooldown_s=5`, object TTL 2 s (`ttl_by_kind`), `max_queue=5`, `suppression=True`,
`pause_allows`, `summary_window_s=3`. Detection wording/filters live in `AdapterOptions`
(`min_confidence`, `labels`, `group_detections`, `include_position`, `position_in_key`, `label_priorities`).

**Open team decisions (not bugs; current behaviour is kept until the team decides):**
1. `position_in_key=False`: a chair that moves from centre to right inside the 5 s cooldown is *not* announced again, because the cooldown key ignores the position. Set `position_in_key=True` to announce zone changes.
2. Two chairs in different zones are said as "Two chairs in view." (no position).

### Priorities
`LOW 1 < NORMAL 2 (objects) < HIGH 3 (checkpoints) < USER_REQUEST 4 < CRITICAL 5 (failures)`.
CRITICAL interrupts lower-priority speech; any message can set `interrupt=True`.

## 4. Files

```
guidesync_tts/message.py    Message + Priority
guidesync_tts/adapters.py   any input -> Messages
guidesync_tts/engine.py     Pyttsx3Engine (own thread, interruptible), ConsoleEngine, FakeEngine
guidesync_tts/manager.py    SpeechManager (rules, queue, log, stats)
guidesync_tts/__main__.py   interactive demo
replay.py, sample_sequence.jsonl   baseline vs suppression comparison
tests/                      pytest suite
```

## 5. Status of real-device checks

Not yet tried on a real laptop - fill in after testing:

- [ ] Real voice `/check` heard through earphones (voice: ______, rate: ______)
- [ ] `/det chair 0.9 left` then quickly `/sys camera_lost` interrupts within 2 s (measured: ______ s)
- [ ] `/pause`, `/repeat`, `/summary` behave as described above

## 6. Known limits

* Real SAPI5 audio could not be tested in the build environment (no sound device or voices there).
  The pyttsx3 wrapper is tested against a mock; your `/check` run is the real verification.
* Interrupting SAPI5 mid-sentence can take ~0.1–0.3 s; the engine is rebuilt after each interrupt
  for reliability. Check that delay against the 2 s failure-notice target.
* One audio output only; no spatial audio, no translation, English phrasing only.
