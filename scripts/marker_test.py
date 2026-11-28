"""Standalone ArUco marker detection distance/hit-rate test."""
import os
import time

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2
import numpy as np

CAM_INDEX = int(os.environ.get("CAM_INDEX", "0"))
WIDTH, HEIGHT = 1920, 1080  # 1280x720 1st round, 1920x1080 2nd round


def main() -> None:
    """Open live camera preview and report ArUco marker detection rate."""
    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_MSMF)
    aruco = cv2.aruco
    detector = aruco.ArucoDetector(
        aruco.getPredefinedDictionary(aruco.DICT_4X4_50),
        aruco.DetectorParameters(),
    )

    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, 30)

        print("Press s to save a picture, r to reset counters, q to quit")
        tries, hits = 0, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Lost the camera")
                break

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners, ids, _ = detector.detectMarkers(gray)
            tries += 1
            if ids is not None:
                hits += 1
                aruco.drawDetectedMarkers(frame, corners, ids)
                c = corners[0][0]
                px = np.linalg.norm(c[0] - c[1])
                cv2.putText(frame, f"{px:.0f} px", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            else:
                cv2.putText(frame, "NOT DETECTED", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            cv2.imshow("marker test", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print(f"Detected in {hits} of {tries} frames ({100 * hits / max(tries, 1):.0f}%)")
                break
            if key == ord("s"):
                name = f"marker_{int(time.time())}.png"
                cv2.imwrite(name, frame)
                print("Saved", name)
            if key == ord("r"):
                print(f"Result: {hits}/{tries} = {100 * hits / max(tries, 1):.0f}%")
                tries, hits = 0, 0
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
