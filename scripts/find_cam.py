import cv2

for i in range(4):
    cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
    ok, frame = cap.read()
    print(i, "works" if ok else "no image", frame.shape if ok else "")
    cap.release()