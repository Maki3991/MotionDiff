# MotionDiff Product Requirements (Draft)

- Status: Local squat AI prototype runnable; human usefulness review and VPS deployment pending
- Last updated: 2026-10-03

## 1. Product goal
Help a participant compare one recorded squat with a prepared reference squat. The current supported action is a single complete side-view squat; the system extracts body pose data, compares the movement phases, and presents local evidence plus optional AI-written, reference-relative suggestions.

## 2. Product shape
The front end may organize a broad catalog of sports and movements, including basketball, football, and fitness. This catalog is a navigation and product-structure goal. It does not mean the first version analyzes all those sports.

The legacy `test2` standing side-leg-raise sequence remains a generic comparison regression baseline. The current user flow uses the supported squat action and requires one complete repetition per clip. Other movements remain planned or unavailable until their action rules exist.

## 3. Intended demo workflow
1. A user selects a reference squat video and a student squat video in the browser.
2. The application processes both videos with MediaPipe Pose Landmarker and keeps source video, per-frame JSON and run metadata.
3. The evidence layer extracts standing/descent/bottom/ascent/finish windows from the single repetition.
4. The comparison module preserves the generic findings; the optional AI provider receives derived metrics and limited evidence screenshots.
5. The result view presents the AI summary/suggestions directly below the keypoint preview, retaining videos, similarity index, localized differences and evidence seek controls.

The capture and processing interaction is record-then-process for the initial demo. Default upload admission is 60 seconds and 50 MiB per clip, with one active upload/analysis and a bounded frame-pair budget. Acceptable wait time remains TBD pending runtime benchmarking; admission does not validate long-sequence analysis.

## 4. Requirements

### P0: Framework and first supported action
- Provide an end-to-end path for single side-view squat clips with optional evidence-linked AI suggestions; keep the legacy generic comparison baseline.
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

## 6. Next iteration (human review pending)

Prioritize review and improvement of the existing report against its paired reference/student video evidence. The next result should let a team reviewer confirm or reject each leading difference by body part, side, matched timestamps, direction and uncertainty. Refine ranking or wording only when that review supports the change; the similarity index remains exploratory. Use fresh recordings of the currently supported action for acceptance.

Camera/viewpoint comparability detection is a later TODO. Existing short clips complete in under 20 seconds per pair on this computer, so the current plan is to evaluate comparability after full extraction before adding an early-abort preview. No 60%/70% similarity cutoff can be treated as a camera-error classifier. Continue to prescribe similar camera direction, height and distance; longer clips and a labelled camera-variation set may justify revisiting this order. The work split and its unfinished tasks are tracked in [STATUS.md](STATUS.md).

## 7. Open product decisions
See docs/DECISIONS.md. The first action and current MediaPipe prototype are selected for this implementation; score calibration, camera tolerance, semantic action alignment and fresh-recording acceptance remain unverified.
