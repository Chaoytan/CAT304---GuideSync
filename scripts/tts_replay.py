"""Replay a recorded input sequence and compare per-detection baseline vs suppression.

Usage:
    python -m scripts.tts_replay sample_data/tts_sequence.jsonl
    python -m scripts.tts_replay sample_data/tts_sequence.jsonl --engine pyttsx3
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.tts import SpeechConfig, create_manager


def run(path: str, suppression: bool, engine: str) -> dict:
    """Replay events from a JSONL file and return stats and spoken texts."""
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
    """Run baseline vs suppression comparison on a recorded JSONL sequence."""
    ap = argparse.ArgumentParser()
    ap.add_argument("sequence", nargs="?", default="sample_data/tts_sequence.jsonl")
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
