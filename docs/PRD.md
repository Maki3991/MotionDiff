# MotionDiff Product Requirements (Draft)

- Status: Local prototype runnable; report-usability improvement planned, new-recording acceptance pending
- Last updated: 2026-10-02

## 1. Product goal
Help a participant compare a recorded movement with a prepared reference movement. The first supported example is the standing side leg raise and arm-raising sequence visible in `videos/test2/A-标准.mp4` and `videos/test2/B-学员.mp4`. The system extracts body pose data from both recordings, compares the movement sequences, and presents an exploratory similarity index with the main joint or clip-progress differences.

## 2. Product shape
The front end may organize a broad catalog of sports and movements, including basketball, football, and fitness. This catalog is a navigation and product-structure goal. It does not mean the first version analyzes all those sports.

The initial implementation compares pre-trimmed clips of the standing side leg raise and arm-raising sequence shown in `test2`. The two clips are not identical in duration or exact repetition timing, so comparison results describe pose differences after whole-clip DTW alignment; they do not verify that the same semantic repetition was aligned. Other movements must be visibly marked as planned, unavailable, or illustrative until their analysis rules exist.

## 3. Intended demo workflow
1. A user selects a coach/reference video and a student video in the local browser app.
2. The application processes both videos with MediaPipe Pose Landmarker and keeps the source video, per-frame JSON and run metadata.
3. A participant recording is expected to follow the same camera direction, approximate height and distance, with one person fully visible.
4. The comparison module normalizes the two sequences, aligns their time progress and computes differences.
5. The result view presents both videos, an exploratory similarity index, localized differences by joint and clip-progress phase, and controls that seek both videos to each difference's evidence timestamps.

The capture and processing interaction is record-then-process for the initial demo. The maximum clip length and acceptable wait time remain TBD pending runtime benchmarking.

## 4. Requirements

### P0: Framework and first supported action
- Provide an end-to-end path for the supported standing side leg raise and arm-raising clips.
- Keep the pose engine behind an adapter so another engine can replace it without rewriting comparison and result presentation.

### P0: Pose data and comparison
- Preserve per-frame raw keypoints with timestamps and confidence values.
- Provide generic normalized keypoints for comparisons.
- Support direct frame/keypoint comparison, normalized feature comparison, and temporal sequence alignment as stages of the comparison pipeline.
- Allow action-specific rules to select keypoints/features and define how differences map to result messages.
- Treat low-confidence or missing keypoints explicitly; do not silently treat them as correct.
- Return an explicit unable-to-judge status if fewer than half of either clip's frames have sufficient landmarks, or fewer than half of the aligned rows contain at least four paired landmarks.

### P0: Result presentation
- Show an overall similarity result.
- Highlight the most relevant joint and/or movement-phase differences.
- Show a pose/skeleton visualization that helps the participant understand the comparison.
- Phrase first-version feedback as relative movement toward the reference video. Do not present it as safety, medical, professional or universal coaching advice.
- Include reference and student timestamps for findings, and allow both videos to be positioned at those timestamps.

## 5. Non-goals for the initial demo
- Analyzing every sport or movement shown in the catalog.
- Guaranteeing viewpoint invariance across arbitrary camera positions.
- Claiming true calibrated 3D reconstruction from one ordinary camera.
- Providing a universal exercise or sports-coaching model.
- Promising real-time performance before testing the selected inference engine on the target laptop.

## 6. Next iteration (selected priority; not implemented)

Prioritize review and improvement of the existing report against its paired reference/student video evidence. The next result should let a team reviewer confirm or reject each leading difference by body part, side, matched timestamps, direction and uncertainty. Refine ranking or wording only when that review supports the change; the similarity index remains exploratory. Use fresh recordings of the currently supported action for acceptance.

Camera/viewpoint comparability detection is a later TODO. Existing short clips complete in under 20 seconds per pair on this computer, so the current plan is to evaluate comparability after full extraction before adding an early-abort preview. No 60%/70% similarity cutoff can be treated as a camera-error classifier. Continue to prescribe similar camera direction, height and distance; longer clips and a labelled camera-variation set may justify revisiting this order. The work split and its unfinished tasks are tracked in [STATUS.md](STATUS.md).

## 7. Open product decisions
See docs/DECISIONS.md. The first action and current MediaPipe prototype are selected for this implementation; score calibration, camera tolerance, semantic action alignment and fresh-recording acceptance remain unverified.
