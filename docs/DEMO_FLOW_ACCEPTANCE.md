# Demo Flow and Acceptance (Draft)

- Status: Squat local AI flow verified with fixed clips; human usefulness review and VPS deployment pending
- Last updated: 2026-10-03

## 1. Target flow
1. Open the local MotionDiff browser app and choose 深蹲.
2. Select one complete side-view reference squat and one student squat.
3. Process both videos with MediaPipe Pose Landmarker, preserving a timestamped JSON record for every decoded frame.
4. Extract squat phase windows and derived metrics; preserve the generic comparison report.
5. Call the configured AI provider with metrics and limited evidence screenshots, then render zero to three validated suggestions below the keypoint preview.
6. Show the original videos, report data and evidence controls even if the AI call fails.

The initial target is record-then-process, not guaranteed live coaching during movement.

## 2. Capture assumptions
- One participant should be visible and sufficiently unobstructed.
- Reference and participant recordings should use the same prescribed camera setup.
- The current supported comparison scope is one complete side-view squat; `videos/test2` is a legacy generic regression baseline.
- Reference and student should use similar side camera direction, height and distance. A single side view cannot establish knee valgus/varus, spinal curvature or injury risk.
- The demo should state the expected framing and action instructions before a new clip is recorded.
- Exact camera height, distance, angle, frame rate, clip duration, and lighting constraints are TBD.

## 3. Acceptance checklist
A demo build is acceptable for the first prototype when:
- Two squat videos can be selected through the browser and processed by MediaPipe.
- Each decoded frame produces a timestamped JSON record, including frames with no detected person.
- The squat flow returns timestamped MediaPipe JSON, a real comparison report and, when configured, a real AI result with server-validated evidence links.
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
- Generic comparison findings still use the existing exploratory 0.10 normalized-position floor. Squat AI suggestions use action evidence windows and provider output validation; neither is a calibrated coaching threshold.
- The 75.4 similarity index on `test2` is uncalibrated and is not a pass/fail threshold.
- Exact camera tolerance and semantic action-mismatch detection remain unsupported.
- The following remain TBD:
- maximum participant clip duration is now 60 seconds by default (2026-10-03); accepted duration does not establish latency or long-sequence accuracy;
- maximum acceptable processing time after recording;
- how many localized differences to show.

## 6. Next report-usability checkpoint (planned, not achieved)

- A named team reviewer checks the leading findings against both linked video times, recording whether joint, side, direction and corresponding clip interval are supported by the footage. Unclear matches are marked uncertain rather than counted as correct.
- With a fresh same-action repeat and a fresh deliberate variation outside `test1`/`test2`, check that ordinary variation does not create many unsupported claims and that the intended change is located in the correct body area and interval.
- The result must distinguish measured difference, relative-to-reference suggestion, and limits caused by 2D projection or alignment; it must not label the uncalibrated index as a pass/fail score.
- Automatic camera/viewpoint mismatch warning and a retry/continue choice remain deferred TODOs. They have no acceptance threshold yet and are not part of the current working app. See [STATUS.md](STATUS.md).
