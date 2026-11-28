"""Stress test: interrupt speech repeatedly and check that speech never gets stuck or silent.

    python stress_interrupt.py                 # real voice, 10 rounds (default engine settings)
    python stress_interrupt.py --rounds 20
    python stress_interrupt.py --recreate      # compare with the slower rebuild-after-interrupt mode
    python stress_interrupt.py --engine console   # no audio, logic only

Each round: start a long sentence, cut it off 0.6 s later with the camera-lost notice, then say a
normal sentence and check that it is spoken too. Listen as well: every round should play the
beginning of the long sentence, then the camera notice, then "Round N finished."
"""
import argparse
import sys
import time

from guidesync_tts import SpeechConfig, create_manager

LONG = ("This is a deliberately long sentence that will be interrupted before it finishes, "
        "so keep listening for the camera notice.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--engine", default="pyttsx3", choices=["pyttsx3", "console"])
    ap.add_argument("--recreate", action="store_true")
    args = ap.parse_args()

    tts = create_manager(args.engine, SpeechConfig(), recreate_on_interrupt=args.recreate)
    tts.say("Stress test starting.", priority="HIGH")
    tts.wait_until_idle(15)

    lat, problems = [], 0
    for i in range(1, args.rounds + 1):
        tts.clear_cooldowns()
        tts.say(LONG, key=f"long{i}")
        time.sleep(0.6)
        tts.submit({"type": "system", "event": "camera_lost"})
        if not tts.wait_until_idle(20):
            print(f"round {i}: FAIL - notice never finished (speech stuck?)")
            problems += 1
            continue
        notice = [e for e in tts.spoken_log() if e["text"].startswith("Camera disconnected")]
        if len(notice) < i:
            print(f"round {i}: FAIL - camera notice was not spoken")
            problems += 1
            continue
        lat.append(notice[-1]["latency_s"])
        tts.say(f"Round {i} finished.", key=f"done{i}")
        if not tts.wait_until_idle(20) or not any(
                e["text"] == f"Round {i} finished." for e in tts.spoken_log()):
            print(f"round {i}: FAIL - speech after the interrupt did not play")
            problems += 1
            continue
        print(f"round {i}: ok, camera notice started {lat[-1]:.2f} s after it was submitted")

    tts.close()
    if lat:
        s = sorted(lat)
        print(f"\nnotice delay: median {s[len(s) // 2]:.2f} s, worst {s[-1]:.2f} s (target: median <= 2 s)")
    print("RESULT:", "PASS" if problems == 0 else f"{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
