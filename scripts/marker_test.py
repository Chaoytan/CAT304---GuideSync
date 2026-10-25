import os
os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
import cv2, time
import numpy as np

CAM = 2 #change with selected camera
WIDTH, HEIGHT = 1280, 720   # try 1920, 1080 in the second round

cap = cv2.VideoCapture(CAM, cv2.CAP_MSMF)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
cap.set(cv2.CAP_PROP_FPS, 30)

aruco = cv2.aruco
detector = aruco.ArucoDetector(
    aruco.getPredefinedDictionary(aruco.DICT_4X4_50),
    aruco.DetectorParameters())

print("Press s to save a picture, q to quit")
while True:
    ok, frame = cap.read()
    if not ok:
        print("Lost the camera")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    if ids is not None:
        aruco.drawDetectedMarkers(frame, corners, ids)
        c = corners[0][0]
        px = np.linalg.norm(c[0] - c[1])   # width of the marker in pixels
        cv2.putText(frame, f"{px:.0f} px", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    else:
        cv2.putText(frame, "NOT DETECTED", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

    cv2.imshow("marker test", frame)
    key = cv2.waitKey(1) & 0xFF
    if key == ord("q"):
        break
    if key == ord("s"):
        name = f"marker_{int(time.time())}.png"
        cv2.imwrite(name, frame)
        print("Saved", name)

cap.release()
cv2.destroyAllWindows()