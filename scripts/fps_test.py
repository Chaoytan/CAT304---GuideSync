"""Benchmark camera FPS across DSHOW and MSMF backends and resolutions."""
import os
import time

import cv2

CAM_INDEX = int(os.environ.get("CAM_INDEX", "0"))


def benchmark_mode(backend: int, name: str, width: int, height: int) -> None:
    """Measure average FPS over 5 seconds for a given backend and resolution."""
    cap = cv2.VideoCapture(CAM_INDEX, backend)
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        for _ in range(10):
            cap.read()  # warm up

        frames, t0 = 0, time.time()
        while time.time() - t0 < 5:
            ok, _ = cap.read()
            if ok:
                frames += 1

        codec = int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode(errors="replace")
        print(f"{name} {width}x{height}: {frames / 5:.1f} FPS (codec: {codec})")
    finally:
        cap.release()


def main() -> None:
    """Run FPS benchmarks across common resolutions."""
    for backend, name in ((cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF")):
        for width, height in ((640, 480), (1280, 720), (1920, 1080)):
            benchmark_mode(backend, name, width, height)


if __name__ == "__main__":
    main()
