# Demo Flow and Acceptance (Draft)

- Status: Fixed `test2` end-to-end run verified; fresh-recording acceptance pending
- Last updated: 2026-10-02

## 1. Target flow
1. Open the local MotionDiff browser app.
2. Select the coach/reference video A and student video B.
3. Process both videos with MediaPipe Pose Landmarker, preserving a timestamped JSON record for every decoded frame.
4. Normalize the visible body landmarks, align the sequences in time with DTW and compute joint position and angle differences.
5. Present the two videos, an exploratory similarity index, and the leading joint/clip-progress differences with evidence timestamps that seek both videos.

The initial target is record-then-process, not guaranteed live coaching during movement.

## 2. Capture assumptions
- One participant should be visible and sufficiently unobstructed.
- Reference and participant recordings should use the same prescribed camera setup.
- The first supported comparison scope is the standing side-leg-raise and arm-raising sequence in `videos/test2`.
- The two `test2` videos show different people with similar frontal framing, but have different durations and repetition timing. Whole-clip DTW is not a semantic repetition detector.
- The demo should state the expected framing and action instructions before a new clip is recorded.
- Exact camera height, distance, angle, frame rate, clip duration, and lighting constraints are TBD.

## 3. Acceptance checklist
A demo build is acceptable for the first prototype when:
- The two `test2` videos can be selected through the browser and processed by MediaPipe.
- Each decoded frame produces a timestamped JSON record, including frames with no detected person.
- `test2` returns timestamped MediaPipe JSON for every decoded frame and a real comparison report.
- The result view can play both source videos, name the main differing joint and clip-progress segment, and seek to both aligned evidence timestamps.
- No person or insufficient valid landmarks produces a clear `insufficient_data` / unable-to-judge state with reasons and no similarity index or findings.
- Fresh-recording acceptance must use a newly recorded sample outside `test2`, under the agreed capture instructions, and be reviewed by a named team member. It remains pending.
- Acceptance examples should include an ordinary repeat that does not produce unsupported findings, and a deliberate visible change that is localized to the correct side and interval.
- Processing latency and clip length are measured on the actual demo laptop and reported honestly.

## 4. Failure cases to handle
- Camera permission denied or camera unavailable.
- No person detected, multiple people detected, or person leaves the frame.
- Important keypoints are missing or confidence is too low.
- Clip cannot be decoded or is outside the supported duration/format.
- Processing exceeds the measured demo wait limit.

## 5. Current prototype thresholds and open targets
- Current quality gate: at least 50% valid normalized frames in each input and at least 50% of DTW aligned rows with four or more paired landmarks. These are conservative prototype gates, not validated accuracy thresholds.
- Current point filter: MediaPipe visibility and presence must each be at least 0.5 when present.
- Current main-finding floor: mean difference of 0.10 shoulder widths. On the existing same-person test1 A/B repeat this removed all finding cards; one A/C lower-camera wrist finding remained, while A/D raised-arm footage ranked the changed-side wrist first. This is evidence from one small control set, not a calibrated tolerance.
- The 75.4 similarity index on `test2` is uncalibrated and is not a pass/fail threshold.
- Exact camera tolerance and semantic action-mismatch detection remain unsupported.
- The following remain TBD:
- maximum participant clip duration;
- maximum acceptable processing time after recording;
- how many localized differences to show.
