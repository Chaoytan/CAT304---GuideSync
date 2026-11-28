"""Interactive demo / manual test:  python -m guidesync_tts [--engine pyttsx3|console] [options]

Type anything at the prompt. Commands start with "/":

  /check                   list installed voices and say a test sentence
  /det chair 0.9 left      send a fake detection (label, confidence, left|centre|right)
  /marker 1 Junction A | The planned route continues left.
  /marker unknown          unrecognised marker
  /sys camera_lost         system event (CRITICAL, interrupts speech)
  /spam chair 20           send the same detection 20 times, 100 ms apart (tests cooldown)
  /json {"text": "Hi", "priority": "high"}    any dict/JSON the adapters understand
  /repeat  /summary        the user-request controls
  /pause   /resume
  /lat                     submit -> speech-start time of the last 5 spoken messages
  /trace                   timeline of the last events (where did the delay come from?)
  /stats   /log FILE.csv
  /quit

Anything else is spoken as plain text.
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import time

from . import SpeechConfig, UnsupportedInputError, create_manager

POS_X = {"left": 100, "centre": 320, "center": 320, "right": 540}


def _print_results(results) -> None:
    for r in results:
        flag = "ok " if r.accepted else "DROP"
        print(f"  [{flag}] {r.reason:<16} {r.message.text!r}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="guidesync_tts", description="GuideSync TTS demo")
    p.add_argument("--engine", default="pyttsx3", choices=["pyttsx3", "console"])
    p.add_argument("--rate", type=int, default=160, help="words per minute (default 160)")
    p.add_argument("--volume", type=float, default=None, help="0.0-1.0")
    p.add_argument("--voice", default="zira", help="substring of voice name (default zira)")
    p.add_argument("--cooldown", type=float, default=5.0)
    p.add_argument("--object-ttl", type=float, default=2.0)
    p.add_argument("--no-suppression", action="store_true", help="baseline: announce every detection")
    p.add_argument("--recreate", action="store_true",
                   help="rebuild the speech engine after an interrupt (slower; only if speech gets stuck)")
    p.add_argument("--no-recreate", action="store_true", help="(default, kept for compatibility)")
    args = p.parse_args(argv)

    cfg = SpeechConfig(cooldown_s=args.cooldown, suppression=not args.no_suppression)
    cfg.ttl_by_kind["object"] = args.object_ttl
    try:
        tts = create_manager(args.engine, cfg, rate=args.rate, volume=args.volume, voice=args.voice,
                             recreate_on_interrupt=args.recreate and not args.no_recreate)
    except ImportError as exc:
        print(f"ERROR: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: could not start the speech engine: {exc!r}")
        print("Try:  python -m guidesync_tts --engine console   (no audio) to test the logic only.")
        return 2

    print(__doc__)
    tts.say("GuideSync speech module ready.", priority="HIGH")
    try:
        while True:
            try:
                line = input("tts> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if not line.startswith("/"):
                _print_results(tts.submit(line))
                continue
            cmd, _, rest = line[1:].partition(" ")
            rest = rest.strip()
            try:
                if cmd in ("quit", "q", "exit"):
                    break
                elif cmd == "check":
                    eng = tts.engine
                    for v in eng.list_voices():
                        print(f"  voice: {v['name']}  ({v['id']})")
                    _print_results(tts.say("Speech check. Can you hear this clearly?", priority="HIGH"))
                elif cmd == "det":
                    parts = rest.split() or ["chair", "0.9", "centre"]
                    label = parts[0]
                    conf = float(parts[1]) if len(parts) > 1 else 0.9
                    x = POS_X.get(parts[2], 320) if len(parts) > 2 else 320
                    _print_results(tts.submit({"label": label, "confidence": conf,
                                               "bbox": [x - 40, 100, x + 40, 300], "frame_width": 640}))
                elif cmd == "marker":
                    if rest == "unknown":
                        _print_results(tts.submit({"type": "marker", "status": "unknown"}))
                    else:
                        head, _, route = rest.partition("|")
                        mid, _, name = head.strip().partition(" ")
                        _print_results(tts.submit({"type": "marker", "marker_id": int(mid),
                                                   "name": name.strip() or None,
                                                   "route_text": route.strip() or None}))
                elif cmd == "sys":
                    _print_results(tts.submit({"type": "system", "event": rest or "camera_lost"}))
                    if rest == "camera_lost":
                        n = tts.cancel_pending(["object"], interrupt_current=False, reason="camera_lost")
                        print(f"  cancelled {n} pending object message(s)")
                elif cmd == "spam":
                    label, _, n = rest.partition(" ")
                    for _ in range(int(n or 20)):
                        tts.submit({"label": label or "chair", "confidence": 0.9,
                                    "bbox": [280, 100, 360, 300], "frame_width": 640})
                        time.sleep(0.1)
                    print("  done (check /stats for how many were suppressed)")
                elif cmd == "json":
                    _print_results(tts.submit(json.loads(rest)))
                elif cmd == "repeat":
                    _print_results([tts.repeat_last()])
                elif cmd == "summary":
                    _print_results([tts.request_summary()])
                elif cmd == "pause":
                    tts.pause()
                    print("  paused")
                elif cmd == "resume":
                    tts.resume()
                    print("  resumed")
                elif cmd == "lat":
                    # submit -> speech onset for the last few spoken messages (the 2 s target)
                    for e in tts.spoken_log()[-5:]:
                        print(f"  {e['latency_s']:.2f} s  {e['text']!r}")
                    timing = getattr(tts.engine, "last_timing", None)
                    if timing:
                        print("  last message, where the time went (seconds): "
                              + ", ".join(f"{k}={v:.2f}" for k, v in timing.items()))
                        print("    engine_init = starting the voice engine, properties = rate/voice setup,")
                        print("    start_delay = from handing text to Windows until sound starts")
                elif cmd == "trace":
                    # timeline of the last events, seconds from the first one shown
                    log = tts.get_log()[-14:]
                    base = log[0]["t"] if log else 0.0
                    for e in log:
                        extra = ""
                        if e["event"] == "spoken" and "onset" in e:
                            extra = f"   (sound started at t={e['onset'] - base:.2f}, ended t={e['end'] - base:.2f})"
                        print(f"  t={e['t'] - base:6.2f}  {e['event']:<12} {e.get('reason', ''):<12} "
                              f"{e.get('text', '')!r}{extra}")
                elif cmd == "stats":
                    print(json.dumps(tts.stats(), indent=2))
                elif cmd == "log":
                    tts.export_log(rest or "tts_log.csv")
                    print(f"  wrote {rest or 'tts_log.csv'}")
                else:
                    print("  unknown command")
            except (UnsupportedInputError, ValueError, IndexError) as exc:
                print(f"  input error: {exc}")
    finally:
        tts.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
