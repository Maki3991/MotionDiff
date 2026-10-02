# Demo Flow and Acceptance (Draft)

- Status: Prototype acceptance; runtime thresholds pending broader benchmark
- Last updated: 2026-10-02

## 1. Target flow
1. Open the local MotionDiff browser app.
2. Select the coach/reference video A and student video B.
3. Process both videos with MediaPipe Pose Landmarker, preserving a timestamped JSON record for every decoded frame.
4. Normalize the visible body landmarks, align the sequences in time with DTW and compute joint position and angle differences.
5. Present the two videos, an exploratory similarity index, and the leading joint/phase differences.

The initial target is record-then-process, not guaranteed live coaching during movement.

## 2. Capture assumptions
- One participant should be visible and sufficiently unobstructed.
- Reference and participant recordings should use the same prescribed camera setup.
- The first action is the standing side leg raise with accompanying arm movement in `videos/test2`.
- The demo should state the expected framing and action instructions before a new clip is recorded.
- Exact camera height, distance, angle, frame rate, clip duration, and lighting constraints are TBD.

## 3. Acceptance checklist
A demo build is acceptable for the first prototype when:
- The two `test2` videos can be selected through the browser and processed by MediaPipe.
- Each decoded frame produces a timestamped JSON record, including frames with no detected person.
- The comparison returns an exploratory index and localized differences for visible shoulders, elbows, wrists, hips, knees or ankles.
- The result view can play both source videos and names the main differing joint and action-progress segment.
- An invalid file, missing person or insufficient landmarks produces a clear failure or unable-to-judge state.
- A new recording made by a different person under the same camera instructions can be submitted for the team's follow-up acceptance check.
- Processing latency and clip length are measured on the actual demo laptop and reported honestly.

## 4. Failure cases to handle
- Camera permission denied or camera unavailable.
- No person detected, multiple people detected, or person leaves the frame.
- Important keypoints are missing or confidence is too low.
- Clip cannot be decoded or is outside the supported duration/format.
- Processing exceeds the measured demo wait limit.

## 5. Thresholds not yet set
Do not invent acceptance numbers before measuring the selected engine on the target laptop. The following remain TBD:
- maximum participant clip duration;
- maximum acceptable processing time after recording;
- minimum keypoint-confidence/coverage threshold;
- score range and score interpretation;
- how many localized differences to show.
