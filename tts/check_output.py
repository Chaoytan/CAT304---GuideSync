"""Checks the sentences GuideSync would speak, then (optionally) speaks them.

    python check_output.py            # text check only, no sound
    python check_output.py --speak    # also reads every sentence aloud with your real voice
"""
import sys

from guidesync_tts import AdapterOptions, SpeechConfig, create_manager, normalize

FIVE = ["person", "chair", "dining table", "backpack", "bottle"]
OPTS = AdapterOptions(labels=FIVE, min_confidence=0.5)


def det(label, x, conf=0.9):
    """A fake detection whose box centre is at x in a 600-pixel-wide frame."""
    return {"label": label, "confidence": conf, "bbox": [x - 20, 50, x + 20, 300], "frame_width": 600}


# (description, input, expected sentences in order)
CASES = [
    ("person, left",            det("person", 100),        ["Person, left of view."]),
    ("chair, centre",           det("chair", 300),         ["Chair, centre of view."]),
    ("dining table, right",     det("dining table", 500),  ["Dining table, right of view."]),
    ("backpack, left",          det("backpack", 100),      ["Backpack, left of view."]),
    ("bottle, right",           det("bottle", 500),        ["Bottle, right of view."]),
    ("two people, same side",   [det("person", 80), det("person", 120)], ["Two people, left of view."]),
    ("two chairs, split sides", [det("chair", 80), det("chair", 520)],   ["Two chairs, left and right of view."]),
    ("three bottles",           [det("bottle", 300)] * 3,  ["Three bottles, centre of view."]),
    ("mixed objects",           [det("person", 100), det("bottle", 500)],
                                ["Person, left of view.", "Bottle, right of view."]),
    # --- the Object Detection module's own format (zone + box_xyxy + timestamp) ---
    ("detector record, zone right", {"class_name": "chair", "confidence": 0.82, "zone": "right",
                                     "box_xyxy": (500, 100, 600, 300), "timestamp": 1.0},
                                    ["Chair, right of view."]),
    ("detector: zone beats box",    {"class_name": "bottle", "confidence": 0.8, "zone": "left",
                                     "box_xyxy": (500, 100, 600, 300), "frame_width": 640},
                                    ["Bottle, left of view."]),
    ("detector: invalid zone, no width", {"class_name": "person", "confidence": 0.8, "zone": "middle",
                                          "box_xyxy": (500, 100, 600, 300)},
                                         ["Person in view."]),
    ("cat -> ignored",          det("cat", 300),           []),
    ("low confidence -> ignored", det("chair", 300, 0.3),  []),
    ("checkpoint marker",       {"type": "marker", "marker_id": 1, "name": "Junction A",
                                 "route_text": "The planned route continues left."},
                                ["Junction A identified. The planned route continues left."]),
    ("camera lost",             {"type": "system", "event": "camera_lost"},
                                ["Camera disconnected. Object announcements stopped."]),
    ("plain text",              "Hello there",             ["Hello there"]),
]


def main() -> int:
    failures = 0
    print("--- Text check (no sound) ---")
    for name, raw, expected in CASES:
        got = [m.text for m in normalize(raw, OPTS)]
        ok = got == expected
        failures += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        print(f"       got:      {got}")
        if not ok:
            print(f"       expected: {expected}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} text checks passed.")

    if "--speak" in sys.argv:
        print("\n--- Speaking each case aloud ---")
        cfg = SpeechConfig(cooldown_s=0, adapter_options=OPTS)
        with create_manager("pyttsx3", cfg) as tts:
            for name, raw, expected in CASES:
                if not expected:
                    continue
                print(f"Speaking: {name}")
                tts.submit(raw)
                tts.wait_until_idle(15)
    else:
        print("Run again with --speak to hear them.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
