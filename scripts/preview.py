import cv2
import time

CAM = 2 #change with selected camera
cap = cv2.VideoCapture(CAM, cv2.CAP_MSMF)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))  # set this first
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)
print("Got:", cap.get(cv2.CAP_PROP_FRAME_WIDTH), cap.get(cv2.CAP_PROP_FRAME_HEIGHT), cap.get(cv2.CAP_PROP_FPS))

frames, start = 0, time.time()

while True:
    ok, frame = cap.read()
    if not ok:
        print("Lost the camera")
        break
    cv2.imshow("preview", frame)
    frames += 1
    if time.time() - start >= 10:
        print("Real FPS:", frames / (time.time() - start))
        frames, start = 0, time.time()

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()