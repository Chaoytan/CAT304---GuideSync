"""End-to-end simulation of the Object Detection -> TTS hand-over (no camera, no model needed).

Feeds detector-style `Detection` records (zone + box_xyxy + timestamp) tick by tick, including a
camera loss and recovery, into the SpeechManager and checks what is spoken.

    python simulate_detector.py            # silent (prints what would be spoken)
    python simulate_detector.py --speak    # real voice
"""
import sys
import time
from dataclasses import dataclass
from typing import List

from guidesync_tts import SpeechConfig, create_manager


@dataclass
class Detection:          # same fields as the detector's record; not imported from it
    frame_id: int
    timestamp: float
    class_name: str
    confidence: float
    box_xyxy: tuple
    zone: str


@dataclass
class Tick:
    frame_id: int
    timestamp: float
    camera_status: str
    detections: List[Detection]


BOX = {"left": (20, 100, 120, 300), "centre": (280, 100, 360, 300), "right": (500, 100, 600, 300)}


def scenario(t):
    """What the fake detector 'sees' t seconds into the run (8 s long)."""
    if t < 3:
        return "ok", [("chair", "right")]
    if t < 5:
        return "ok", [("chair", "right"), ("person", "left")]
    if t < 6.5:
        return "lost", []
    return "ok", [("backpack", "left")]


def main() -> int:
    engine = "pyttsx3" if "--speak" in sys.argv else "console"
    tts = create_manager(engine, SpeechConfig())
    start = time.monotonic()
    frame, submitted_ticks, lost_sent = 0, 0, False
    while True:
        now = time.monotonic()
        t = now - start
        if t > 8:
            break
        status, items = scenario(t)
        tick = Tick(frame, now, status, [Detection(frame, now, c, 0.85, BOX[z], z) for c, z in items])
        if tick.camera_status == "lost":
            if not lost_sent:
                tts.cancel_pending(["object"])
                tts.submit({"type": "system", "event": "camera_lost"})
                lost_sent = True
        elif tick.detections:
            tts.submit(tick.detections)
            submitted_ticks += 1
        frame += 1
        time.sleep(0.05)                  # ~20 frames per second
    tts.wait_until_idle(10)

    log = tts.get_log()
    spoken = [e for e in log if e["event"] == "spoken"]
    texts = [e["text"] for e in spoken]
    lost_at = next(e["t"] for e in log if e["event"] == "submitted" and "Camera" in e.get("text", ""))
    objects_during_loss = [e for e in spoken if e["kind"] == "object"
                           and lost_at <= e["onset"] <= lost_at + 1.5]
    stats = tts.stats()
    tts.close()

    print("\nSpoken, in order:")
    for x in texts:
        print("  -", x)
    print(f"\nframes with detections sent: {submitted_ticks}   spoken: {stats['spoken']}   "
          f"dropped: {stats['dropped']}")
    print(f"latency from frame: median={stats['latency_median_s']:.3f}s  p95={stats['latency_p95_s']:.3f}s")

    checks = [
        ("zone is spoken ('Chair, right of view.')", "Chair, right of view." in texts),
        ("person zone is spoken", "Person, left of view." in texts),
        ("camera-loss notice spoken", any(t.startswith("Camera disconnected") for t in texts)),
        ("no object announced right after camera loss", not objects_during_loss),
        ("backpack announced after recovery", "Backpack, left of view." in texts),
        ("far fewer messages spoken than frames sent", stats["spoken"] < submitted_ticks / 10),
        ("no 'in view' without a position", not any(t.endswith(" in view.") for t in texts)),
    ]
    bad = 0
    print()
    for name, ok in checks:
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
