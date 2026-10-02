# Demo Flow and Acceptance (Draft)

- Status: Draft; runtime thresholds pending benchmark
- Last updated: 2026-10-02

## 1. Target flow
1. Load the prepared reference video and its precomputed pose sequence.
2. Show the participant the capture instructions for the selected action and camera setup.
3. Record the participant with the same demo camera setup.
4. Stop recording and process the clip.
5. Compare pose sequences through the agreed stages: direct data comparison, normalized feature comparison, and temporal alignment.
6. Present a pose visualization, overall similarity score, and the leading joint/phase differences.

The initial target is record-then-process, not guaranteed live coaching during movement.

## 2. Capture assumptions
- One participant should be visible and sufficiently unobstructed.
- Reference and participant recordings should use the same prescribed camera setup.
- The demo should state the expected framing and action instructions after the action is selected.
- Exact camera height, distance, angle, frame rate, clip duration, and lighting constraints are TBD.

## 3. Acceptance checklist
A demo build is acceptable for the chosen action when:
- The reference pose sequence can be loaded without reprocessing the reference video during the participant's turn.
- A participant clip can be captured and submitted for processing.
- The system produces a timestamped pose sequence or a clear processing failure.
- The comparison returns an overall score and localized joint/phase differences.
- The result view can render the pose visualization and comparison output.
- Unsupported movements are visibly marked and cannot be mistaken for supported analysis.
- Processing latency and clip length have been measured on the actual demo laptop and are displayed or communicated honestly.

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