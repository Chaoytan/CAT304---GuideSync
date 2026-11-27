"""Replay a recorded input sequence and compare per-detection baseline vs suppression.

Usage:
    python replay.py sample_sequence.jsonl                 # silent (console engine, fast)
    python replay.py sample_sequence.jsonl --engine pyttsx3

Each line of the file:   {"t": 0.5, "input": <anything the adapters accept>}
"t" is seconds from the start of the run. This is the "same recorded sequence, with and
without suppression" comparison from section 5.3 of the proposal (message counts only;
correctness against ground truth still has to be judged by you).
"""
from __future__ import annotations

import argparse
import json
import time

from guidesync_tts import SpeechConfig, create_manager


def run(path: str, suppression: bool, engine: str) -> dict:
    cfg = SpeechConfig(suppression=suppression)
    tts = create_manager(engine, cfg)
    with open(path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    start = time.monotonic()
    for ev in events:
        delay = ev["t"] - (time.monotonic() - start)
        if delay > 0:
            time.sleep(delay)
        tts.submit(ev["input"])
    tts.wait_until_idle(30)
    stats = tts.stats()
    spoken = [e["text"] for e in tts.spoken_log()]
    tts.close()
    return {"stats": stats, "spoken": spoken}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sequence")
    ap.add_argument("--engine", default="console", choices=["console", "pyttsx3"])
    args = ap.parse_args()

    for label, supp in (("BASELINE (no suppression)", False), ("PROPOSED (suppression)", True)):
        res = run(args.sequence, supp, args.engine)
        s = res["stats"]
        print(f"\n=== {label} ===")
        print(f"submitted={s['submitted']}  spoken={s['spoken']}  dropped={s['dropped']}")
        print(f"latency median={s['latency_median_s']}  p95={s['latency_p95_s']}")


if __name__ == "__main__":
    main()
