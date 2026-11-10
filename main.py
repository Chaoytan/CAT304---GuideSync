"""GuideSync - run the full pipeline: camera -> detection -> analysis -> voice.

Examples:
    python main.py                      # live camera (CAM_INDEX env var or config.py)
    python main.py --source 1           # camera index 1
    python main.py --source demo.mp4    # video file
    python main.py --mock --no-voice    # no YOLO, fake detections
Keys in the preview window: q = quit, m = mute/unmute voice.
"""
import argparse
import csv
import os
import time
from datetime import datetime

import cv2

import config
from modules.camera import Camera
from modules.detection import MockDetector, YoloDetector
from modules.obstacle_analyzer import ObstacleAnalyzer
from modules.voice_guidance import PrintBackend, VoiceGuidance
from ui import dashboard


def parse_args():
    p = argparse.ArgumentParser(description="GuideSync navigation assistant")
    p.add_argument("--source", default=None, help="camera index or video path")
    p.add_argument("--mock", action="store_true", help="use fake detections instead of YOLO")
    p.add_argument("--no-voice", action="store_true", help="print messages instead of speaking")
    p.add_argument("--no-ui", action="store_true", help="do not open the preview window")
    return p.parse_args()


def main():
    args = parse_args()
    source = args.source
    if source is not None and source.isdigit():
        source = int(source)

    detector = MockDetector() if args.mock else YoloDetector()
    analyzer = ObstacleAnalyzer()
    if args.no_voice:
        voice = VoiceGuidance(backend_factory=PrintBackend).start()
    else:
        voice = VoiceGuidance().start()

    os.makedirs(config.LOG_DIR, exist_ok=True)
    log_path = os.path.join(config.LOG_DIR, f"run_{datetime.now():%Y%m%d_%H%M%S}.csv")
    log_file = open(log_path, "w", newline="")
    log = csv.writer(log_file)
    log.writerow(["time", "fps", "latency_ms", "n_detections", "message"])

    fps, frame_no, last_detections = 0.0, 0, []
    try:
        with Camera(source) as cam:
            print("Running. Press q in the window (or Ctrl+C) to stop.")
            while True:
                t0 = time.perf_counter()
                frame = cam.read()
                if frame is None:
                    print("Video source ended or camera lost.")
                    break

                h, w = frame.shape[:2]
                if frame_no % config.DETECT_EVERY_N_FRAMES == 0:
                    last_detections = detector.detect(frame)
                frame_no += 1

                decision = analyzer.analyze(last_detections, (w, h))
                if decision:
                    voice.speak(decision)

                dt = time.perf_counter() - t0
                fps = 0.9 * fps + 0.1 * (1 / dt) if fps else 1 / dt
                log.writerow([f"{time.time():.3f}", f"{fps:.1f}", f"{dt * 1000:.0f}",
                              len(last_detections), decision["message"] if decision else ""])

                if not args.no_ui:
                    view = dashboard.draw(frame, last_detections, decision, fps, dt * 1000, voice.muted)
                    cv2.imshow("GuideSync", view)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        break
                    if key == ord("m"):
                        voice.unmute() if voice.muted else voice.mute()
    except KeyboardInterrupt:
        pass
    finally:
        voice.stop()
        log_file.close()
        cv2.destroyAllWindows()
        print(f"Log saved to {log_path}")


if __name__ == "__main__":
    main()
