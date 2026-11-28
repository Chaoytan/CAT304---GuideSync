"""Run from the repository root: python -m scripts.checkpoint_demo"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from modules.direction_checkpoint import MarkerReader, Route, locate_objects
from modules.lounge import LoungeRoute


def _run_sample(route: Route | LoungeRoute, use_lounge: bool) -> None:
    """Print sample object locations and simulated route progression without a camera."""
    print("Sample detections (no camera or YOLO):")
    for x in (40, 280, 520):
        sample = locate_objects(640, 480, [{"label": "chair", "confidence": 0.9, "bbox": [x, 40, x + 80, 140]}])
        print(sample[0]["text"])

    if use_lounge:
        assert isinstance(route, LoungeRoute)
        for side in ("right", "left"):
            route.reset()
            frames = [[10], [20, 30]] + ([[40], [20, 30]] if side == "left" else []) + [[50], [60]]
            for seen in frames:
                event = route.observe(seen)
                print(event["text"])
                if event["status"] == "choice_visible":
                    selection = route.choose(side)
                    if selection:
                        print(selection["text"])
                else:
                    route.confirm(event["expected"])
            print(route.observe([])["status"])
        return

    for ids in ([], [20], [10], [10], [49], [20], [30]):
        event = route.observe(ids)
        print(event)
        if event["status"] == "expected_visible":
            route.confirm(ids[0])  # simulate operator confirmation in this demo


def _generate_markers(route: Route | LoungeRoute, dictionary_name: str, use_lounge: bool) -> None:
    """Generate, verify, and save ArUco marker PNG files for physical desk testing."""
    import cv2

    aruco = cv2.aruco
    dictionary = aruco.getPredefinedDictionary(getattr(aruco, dictionary_name))
    folder = Path("lounge_markers" if use_lounge else "module2_markers")
    folder.mkdir(exist_ok=True)

    for code in route.ids:
        img = aruco.generateImageMarker(dictionary, code, 600)
        img = cv2.copyMakeBorder(img, 80, 80, 80, 80, cv2.BORDER_CONSTANT, value=255)
        _, decoded, _ = aruco.ArucoDetector(dictionary).detectMarkers(img)
        if decoded is None or decoded.flatten().tolist() != [code]:
            raise RuntimeError(f"Generated marker did not decode as {code}")
        path = folder / f"checkpoint_{code}.png"
        if not cv2.imwrite(str(path), img):
            raise OSError(path)
        print(path)


def _run_camera_demo(camera_index: int, route: Route | LoungeRoute, dictionary_name: str, use_lounge: bool) -> None:
    """Open a live camera preview to test ArUco checkpoint confirmation interactively."""
    import cv2

    reader = MarkerReader(dictionary_name)
    cap = cv2.VideoCapture(camera_index, cv2.CAP_MSMF) if os.name == "nt" else cv2.VideoCapture(camera_index)
    try:
        if not cap.isOpened():
            raise RuntimeError("Cannot open camera; check the index and close other previews.")
        if os.name == "nt":
            props = (
                (cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),
                (cv2.CAP_PROP_FRAME_WIDTH, 1920),
                (cv2.CAP_PROP_FRAME_HEIGHT, 1080),
                (cv2.CAP_PROP_FPS, 30),
            )
            for prop, value in props:
                if not cap.set(prop, value):
                    print(f"Camera did not accept property {prop} = {value}")

        print(
            f"Camera reports {cap.get(cv2.CAP_PROP_FRAME_WIDTH):g} x "
            f"{cap.get(cv2.CAP_PROP_FRAME_HEIGHT):g} at {cap.get(cv2.CAP_PROP_FPS):g} FPS"
        )
        print("Desk test: c confirms the visible checkpoint, q quits.")
        if use_lounge:
            print("Junction keys: l = left, r = right, x = reset.")
        else:
            print("r resets route.")

        previous = None
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Camera feed lost; restart demo to reset route.")
            event = route.observe(reader.read(frame))
            if event != previous:
                print(event)
                previous = event

            cv2.putText(frame, event["status"], (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 180, 0), 2)
            cv2.imshow("GuideSync checkpoint desk test", frame)
            key = cv2.waitKey(1) & 0xFF
            if use_lounge and isinstance(route, LoungeRoute) and key in (ord("l"), ord("r")):
                selection = route.choose("left" if key == ord("l") else "right")
                if selection:
                    print(selection)
            if key == ord("q"):
                break
            if key == ord("x" if use_lounge else "r"):
                route.reset()
            if key == ord("c"):
                route.confirm(event["expected"])
    finally:
        cap.release()
        cv2.destroyAllWindows()


def main() -> None:
    """Run the sample, generate markers, or start the standalone camera demo."""
    parser = argparse.ArgumentParser(description="GuideSync Module 2 checkpoint demo")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print-markers", action="store_true")
    mode.add_argument("--camera", type=int)
    parser.add_argument("--lounge", action="store_true", help="Use the six-marker branching route")
    args = parser.parse_args()

    route: Route | LoungeRoute = LoungeRoute() if args.lounge else Route()
    dictionary_name = route.dictionary_name if args.lounge else "DICT_4X4_50"

    if not args.print_markers and args.camera is None:
        _run_sample(route, args.lounge)
        return

    if os.name == "nt":
        os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

    if args.print_markers:
        _generate_markers(route, dictionary_name, args.lounge)
    else:
        _run_camera_demo(args.camera, route, dictionary_name, args.lounge)


if __name__ == "__main__":
    main()
