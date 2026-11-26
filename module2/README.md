# GuideSync Module 2: Direction and Checkpoint
Copy the whole module2 folder alongside scripts/ in your team repository. Run commands from the repository root. This add-on does not replace Module 1 or require YOLO weights.

## First run (Windows terminal)
    python -m module2.demo
    python -m unittest -v module2.test_module module2.test_integration
    & "$HOME\.guidesync-venv\Scripts\python.exe" -m module2.demo --camera 0 OR 1 OR 2 ETC...
    explorer "$HOME\module2_markers"

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
direction_checkpoint.py: locate_objects() divides the non-mirrored image that the boxes refer to into thirds using each box midpoint; MarkerReader.read() reads IDs from the untouched image; Route.observe() looks up the current checkpoint and rejects ambiguous, unknown or out-of-order observations. Route.confirm() advances the route only on explicit confirmation. The route follows the direction listed in route.json, not the reverse route.
demo.py: examples, marker printing and standalone desk testing. Only the standalone camera demo opens the camera.
test_module.py: tests position boundaries, invalid inputs, sequence mistakes, confirmation and reset.

## Team interface
Module 1 owns capture, YOLO and confidence filtering. Supply an unannotated BGR camera frame, detections for that frame (possibly empty), frame ID and monotonic capture time. The proposed detector returns dataclasses with frame_id, timestamp, class_name, confidence, box_xyxy and zone. The boxes are xyxy pixels in the resized, unmirrored whole image. Module 2 derives position using the detector width; it does not use the full camera width or require the upstream zone. Slightly overshooting boxes are clipped, empty or malformed boxes and mismatched IDs are skipped. If cropping, mirroring or letterboxing is introduced, map boxes back to an unpadded, unmirrored whole-frame coordinate system first.

    from module2.direction_checkpoint import MarkerReader, Route, process_frame
    reader, route = MarkerReader(), Route()  # once before the loop
    # Inside the existing camera loop, after detecting in resized_frame:
    dh, dw = resized_frame.shape[:2]
    event = process_frame(frame, detections, frame_id, captured_at, reader, route,
                          detector_size=(dw, dh))

Use your actual variable names. Pass the actual size of the image to which the output boxes refer. If omitted, dataclasses use the proposed 640 x 360; older dictionaries with label/bbox use full-camera coordinates. The frame passed to MarkerReader stays full size. On Windows the standalone demo requests MSMF, MJPG, 1920 x 1080, 30 FPS. Verify the reported mode on your device. Do not open another camera in the integrated code.

event["objects"] returns label, clipped bbox, bbox_size (width, height), position and text, plus confidence and timing fields for Module 1 detections. event["checkpoint"] contains seen IDs, expected ID, status, and text (None if there is no valid cue). Both refer to the outer frame_id and captured_at. Module 3 selects fresh candidate text and handles repetition and playback. Module 4 logs statuses, owns controls and forwards operator confirmation to route.confirm(id) only for the latest fresh expected observation. Reset route and invalidate old events on camera loss or restart. An empty YOLO list must not disable marker detection. Do not call the standalone camera demo from the integrated application.

## What to record for the proposal
For example, run ten three-checkpoint sequences (30 valid individual presentations). For each presentation record expected ID and cue, detected ID, actual delivered message, miss or mismatch, and pass/fail. Count a miss as a failure. At least 27/30 correct meets the proposal's 90% target; do not claim the target from unit tests or a per-frame hit percentage. Also record separate negative trials: no marker, unknown ID, repeated ID, out-of-order ID and two visible IDs. Check left/centre/right with an actual object at each position once Module 1 is connected. Confirm the direction against the wearer's camera view, not a mirrored preview.

## GitHub
On a feature branch, commit the module2 source, configuration, tests and README. Open a pull request and ask the detection and integration teammates to verify the field names with one real frame and detection. Do not commit virtual environments or recordings of people.

## Optional lounge route (original three-marker route stays the default)
Run from the repository root with the project Python:
    python -m module2.demo --lounge
    python -m unittest -v module2.test_module module2.test_integration module2.test_lounge
    python -m module2.demo --lounge --print-markers
    python -m module2.demo --lounge --camera 1

Use the USB camera's actual index. Print the six PNGs from lounge_markers. The generator checks each ID by decoding it before saving. Keep white margins. Place 20 and 30 facing the entrance; print another copy of 30 facing the return approach if necessary. Place 40 before the dead end. Place 50 before the second right turn; 60 at the destination. Validate cues in lounge.json against the actual room. DICT_4X4_50 cannot encode 50 or 60; the lounge generator and reader both use DICT_4X4_100.

In the preview: c confirms an ordinary visible checkpoint, l/r selects left/right only while both 20 and 30 are visible, x resets, q quits. Single junction signs on first approach produce partial_junction, not a selection. Return from 40 accepts 30 alone or the exact pair. Other multi-sign combinations produce no cue. The standalone preview prints cues; it does not play audio or run YOLO. Use a sighted operator for the controlled demo.

Team integration: keep one reader and route outside the shared camera loop:
    from module2.lounge import LoungeRoute
    from module2.direction_checkpoint import MarkerReader, process_frame
    route = LoungeRoute()
    reader = MarkerReader(route.dictionary_name)

Keep the existing process_frame call, using the raw frame and the detector's actual box size. Forward checkpoint text to Module 3, including status choice_visible (not just expected_visible). Module 4 should map l/r to route.choose("left"/"right") and forward its returned event text to Module 3 once when non-None; c uses route.confirm(event["checkpoint"]["expected"]). x resets. On camera loss reset the route, clear queued cues, and require a fresh observation before confirming. Do not call choose or confirm on old frames. A route cue or keyboard selection cannot validate wearer position, orientation, physical arrival or clear walking space.
