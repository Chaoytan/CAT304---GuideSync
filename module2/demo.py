"""Run from the parent directory: python -m module2.demo"""
import argparse
import os
from pathlib import Path
from .direction_checkpoint import locate_objects, MarkerReader, Route

def main() -> None:
    """Run the sample, generate markers, or start the standalone camera demo."""
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--print-markers", action="store_true")
    mode.add_argument("--camera", type=int)
    args = parser.parse_args()
    route = Route()
    if not args.print_markers and args.camera is None:
        print("Sample detections (no camera or YOLO):")
        for x in (40, 280, 520):
            print(locate_objects(640, 480, [dict(label="chair", confidence=.9, bbox=[x,40,x+80,140])])[0]["text"])
        for ids in ([], [20], [10], [10], [49], [20], [30]):
            event = route.observe(ids)
            print(event)
            if event["status"] == "expected_visible":
                route.confirm(ids[0])  # simulate operator confirmation in this demo
        return
    if os.name == "nt":
        os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")
    import cv2
    if args.print_markers:
        a = cv2.aruco
        dictionary = a.getPredefinedDictionary(a.DICT_4X4_50)
        folder = Path("module2_markers")
        folder.mkdir(exist_ok=True)
        for code in route.ids:
            img = a.generateImageMarker(dictionary, code, 600)
            img = cv2.copyMakeBorder(img, 80,80,80,80,cv2.BORDER_CONSTANT,value=255)
            path = folder / f"checkpoint_{code}.png"
            if not cv2.imwrite(str(path), img):
                raise OSError(path)
            print(path)
        return
    reader = MarkerReader()
    cap = (cv2.VideoCapture(args.camera, cv2.CAP_MSMF) if os.name == "nt"
           else cv2.VideoCapture(args.camera))
    try:
        if not cap.isOpened():
            raise RuntimeError("Cannot open camera; check the index and close other previews.")
        if os.name == "nt":
            for prop, value in ((cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG")),
                                (cv2.CAP_PROP_FRAME_WIDTH, 1920), (cv2.CAP_PROP_FRAME_HEIGHT, 1080),
                                (cv2.CAP_PROP_FPS, 30)):
                if not cap.set(prop, value):
                    print(f"Camera did not accept property {prop} = {value}")
        print(f"Camera reports {cap.get(cv2.CAP_PROP_FRAME_WIDTH):g} x "
              f"{cap.get(cv2.CAP_PROP_FRAME_HEIGHT):g} at {cap.get(cv2.CAP_PROP_FPS):g} FPS")
        print("Desk test: c confirms visible expected marker, r resets route, q quits.")
        previous = None
        while True:
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Camera feed lost; restart demo to reset route.")
            event = route.observe(reader.read(frame))
            if event != previous:
                print(event)
                previous = event
            cv2.putText(frame, event["status"], (10,35),cv2.FONT_HERSHEY_SIMPLEX,.8,(0,180,0),2)
            cv2.imshow("GuideSync checkpoint desk test",frame)
            key = cv2.waitKey(1) & 255
            if key == ord("q"): break
            if key == ord("r"): route.reset()
            if key == ord("c"): route.confirm(event["expected"])
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
