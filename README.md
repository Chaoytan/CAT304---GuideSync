# GuideSync Module 2: Direction and Checkpoint
Copy the whole module2 folder alongside scripts/ in your team repository. Run commands from the repository root. This add-on does not replace Module 1 or require YOLO weights.

## First run (Windows terminal)
    python -m module2.demo
    python -m unittest -v module2.test_module

No extra packages needed for those two commands. The three chair lines are sample inputs, not live AI detections. Expected route events include out_of_order and already_confirmed. A visible marker is an observation, not proof that the wearer has arrived.

## Physical desk test
Use the same Python environment that runs the team's scripts/marker_test.py. Check:
    python -c "import cv2; print(cv2.__version__, cv2.aruco.ArucoDetector)"
If this fails, check the selected interpreter with Module 1's owner; use the team's tested OpenCV environment.
    python -m module2.demo --print-markers
Print each PNG on white paper with its white margin intact. The sample route uses dictionary DICT_4X4_50. Stand the three sheets at known demonstration checkpoints. Replace the example names and one-way cues in route.json with your team's actual route before a route demonstration.
    python scripts/find_cam.py
    python -m module2.demo --camera 3
Replace 3 with the external camera index on your laptop. Close the other camera scripts first. Show marker 10, then 20, then 30. In the preview window press c while the expected marker is visible to simulate operator confirmation at that checkpoint; r resets and q quits. Try 30 before 10 and try covering the marker. This demo prints events, does not speak, and does not perform live object detection.

## How the files work
direction_checkpoint.py: locate_objects() divides the original non-mirrored image into thirds using each box midpoint; MarkerReader.read() reads IDs from the untouched image; Route.observe() looks up the current checkpoint and rejects ambiguous, unknown or out-of-order observations. Route.confirm() advances the route only on explicit confirmation. The route follows the direction listed in route.json, not the reverse route.
demo.py: examples, marker printing and standalone desk testing. Only the standalone camera demo opens the camera.
test_module.py: tests position boundaries, invalid inputs, sequence mistakes, confirmation and reset.

## Team interface
Module 1 owns capture, YOLO, confidence filtering. Request an unannotated BGR frame, filtered detections (empty list is valid), frame ID, and original monotonic capture time. The boxes must be in pixels of that same original, non-mirrored frame. Never mix an older detection with a newer frame. If asynchronous, match by ID or discard unmatched results. Clip any out-of-frame boxes upstream; invalid boxes raise ValueError.
Example detection: {"label":"chair","bbox":[100,40,220,140],"confidence":0.91}.
Module 4 creates one reader and one route for the session, then calls the following interface on each fresh matched frame:

    from module2.direction_checkpoint import MarkerReader, Route, process_frame
    reader, route = MarkerReader(), Route()  # once, outside capture loop
    # Inside the team's camera loop, after Module 1:
    event = process_frame(frame, detections, frame_id, captured_at, reader, route)

event["objects"] contains original detection fields plus position and text. event["checkpoint"] contains seen IDs, expected ID, status, and text (None if there is no valid cue). Both refer to the outer frame_id and captured_at. Module 3 selects fresh candidate text and handles repetition and playback. Module 4 logs statuses, owns controls and forwards operator confirmation to route.confirm(id) only for the latest fresh expected observation. Reset route and invalidate old events on camera loss or restart. An empty YOLO list must not disable marker detection. Do not call the standalone camera demo from the integrated application.

## What to record for the proposal
For example, run ten three-checkpoint sequences (30 valid individual presentations). For each presentation record expected ID and cue, detected ID, actual delivered message, miss or mismatch, and pass/fail. Count a miss as a failure. At least 27/30 correct meets the proposal's 90% target; do not claim the target from unit tests or a per-frame hit percentage. Also record separate negative trials: no marker, unknown ID, repeated ID, out-of-order ID and two visible IDs. Check left/centre/right with an actual object at each position once Module 1 is connected. Confirm the direction against the wearer's camera view, not a mirrored preview.

## GitHub
On a feature branch, commit the module2 source, configuration, tests and README. Open a pull request and ask the detection and integration teammates to verify the field names with one real frame and detection. Do not commit virtual environments or recordings of people.
