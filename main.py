"""GuideSync - run the full pipeline: camera -> detection -> analysis/route -> voice.

Examples:
    python main.py                         # live camera (CAM_INDEX env var or config.py)
    python main.py --source 1              # camera index 1
    python main.py --source demo.mp4       # video file
    python main.py --mock --no-voice       # no YOLO, print instead of speak
    python main.py --route basic           # include ArUco checkpoint guidance
    python main.py --route lounge          # include branching lounge route guidance

Keys in the preview window:
    q = quit, m = mute/unmute voice, v = repeat last, s = scene summary
    (with --route): c = confirm checkpoint, l/r = branch choice, x = reset route
"""
from __future__ import annotations

import argparse
import csv
import os
import time
from datetime import datetime

import cv2

import config
from modules.camera import Camera
from modules.detection import MockDetector, YoloDetector
from modules.direction_checkpoint import MarkerReader, Route
from modules.lounge import LoungeRoute
from modules.obstacle_analyzer import ObstacleAnalyzer
from modules.voice_guidance import PrintBackend, VoiceGuidance
from ui import dashboard


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GuideSync navigation assistant")
    p.add_argument("--source", default=None, help="camera index or video path")
    p.add_argument("--mock", action="store_true", help="use fake detections instead of YOLO")
    p.add_argument("--no-voice", action="store_true", help="print messages instead of speaking")
    p.add_argument("--no-ui", action="store_true", help="do not open the preview window")
    p.add_argument(
        "--route",
        default="none",
        choices=("none", "basic", "lounge"),
        help="enable Module 2 ArUco checkpoint route guidance",
    )
    return p.parse_args()


def _init_route(route_mode: str):
    if route_mode == "lounge":
        route = LoungeRoute()
        return route, MarkerReader(route.dictionary_name)
    if route_mode == "basic":
        return Route(), MarkerReader()
    return None, None


def _handle_key(key: int, voice: VoiceGuidance, route, checkpoint: dict | None, route_mode: str) -> bool:
    """Process one OpenCV key press; return False to exit the loop."""
    if key == ord("q"):
        return False
    if key == ord("m"):
        voice.unmute() if voice.muted else voice.mute()
    elif key == ord("v"):
        voice.repeat()
    elif key == ord("s"):
        voice.summary()
    elif route is not None:
        if key == ord("x"):
            route.reset()
        elif key == ord("c") and checkpoint is not None:
            route.confirm(checkpoint.get("expected"))
        elif route_mode == "lounge" and key in (ord("l"), ord("r")):
            selection = route.choose("left" if key == ord("l") else "right")
            if selection:
                voice.speak(selection)
    return True


def main() -> None:
    args = parse_args()
    source = int(args.source) if args.source is not None and args.source.isdigit() else args.source

    detector = MockDetector() if args.mock else YoloDetector()
    analyzer = ObstacleAnalyzer()
    route, reader = _init_route(args.route)
    voice = VoiceGuidance(backend_factory=PrintBackend if args.no_voice else None).start()

    os.makedirs(config.LOG_DIR, exist_ok=True)
    log_path = os.path.join(config.LOG_DIR, f"run_{datetime.now():%Y%m%d_%H%M%S}.csv")

    fps, frame_no, last_detections = 0.0, 0, []
    try:
        with open(log_path, "w", newline="", encoding="utf-8") as log_file, Camera(source) as cam:
            log = csv.writer(log_file)
            log.writerow(["time", "fps", "latency_ms", "n_detections", "message", "checkpoint_status"])
            print("Running. Press q in the window (or Ctrl+C) to stop.")

            while True:
                t0 = time.perf_counter()
                frame = cam.read()
                captured_at = time.monotonic()
                if frame is None:
                    print("Video source ended or camera lost.")
                    voice.cancel_objects("camera_lost")
                    voice.speak({"type": "system", "event": "camera_lost"})
                    if route is not None:
                        route.reset()
                    break

                h, w = frame.shape[:2]
                if frame_no % config.DETECT_EVERY_N_FRAMES == 0:
                    last_detections = detector.detect(frame)
                frame_no += 1

                checkpoint = route.observe(reader.read(frame)) if route is not None and reader is not None else None
                if checkpoint and checkpoint.get("text"):
                    voice.speak(checkpoint, created_at=captured_at)

                decision = analyzer.analyze(last_detections, (w, h))
                if decision:
                    voice.speak(decision, created_at=captured_at)

                dt = time.perf_counter() - t0
                fps = 0.9 * fps + 0.1 * (1 / dt) if fps else 1 / dt
                spoken_text = (
                    checkpoint["text"]
                    if checkpoint and checkpoint.get("text")
                    else (decision["message"] if decision else "")
                )
                log.writerow([
                    f"{time.time():.3f}",
                    f"{fps:.1f}",
                    f"{dt * 1000:.0f}",
                    len(last_detections),
                    spoken_text,
                    checkpoint["status"] if checkpoint else "",
                ])

                if not args.no_ui:
                    view = dashboard.draw(
                        frame,
                        last_detections,
                        decision,
                        fps,
                        dt * 1000,
                        voice.muted,
                        checkpoint=checkpoint,
                    )
                    cv2.imshow("GuideSync", view)
                    key = cv2.waitKey(1) & 0xFF
                    if not _handle_key(key, voice, route, checkpoint, args.route):
                        break
    except KeyboardInterrupt:
        pass
    finally:
        voice.stop()
        cv2.destroyAllWindows()
        print(f"Log saved to {log_path}")


if __name__ == "__main__":
    main()
