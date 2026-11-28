"""Probe camera indices 0-5 using the Windows MSMF backend."""
import cv2


def main() -> None:
    """Print which camera indices return frames and their shape."""
    for idx in range(6):
        cap = cv2.VideoCapture(idx, cv2.CAP_MSMF)
        try:
            ok, frame = cap.read()
            print(idx, "works" if ok else "no image", frame.shape if ok else "")
        finally:
            cap.release()


if __name__ == "__main__":
    main()
