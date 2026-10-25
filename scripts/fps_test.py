import cv2, time

CAM = 2 #change with selected camera

def test(backend, name, w, h):
    cap = cv2.VideoCapture(CAM, backend)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, 30)
    for _ in range(10):
        cap.read()  # warm up
    n, t0 = 0, time.time()
    while time.time() - t0 < 5:
        ok, _ = cap.read()
        if ok:
            n += 1
    codec = int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4, "little").decode(errors="replace")
    print(f"{name} {w}x{h}: {n / 5:.1f} FPS (codec: {codec})")
    cap.release()

for backend, name in [(cv2.CAP_DSHOW, "DSHOW"), (cv2.CAP_MSMF, "MSMF")]:
    for w, h in [(640, 480), (1280, 720), (1920, 1080)]:
        test(backend, name, w, h)