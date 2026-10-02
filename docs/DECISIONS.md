# Decisions and Open Questions

- Last updated: 2026-10-02

## Settled by the team

| ID | Decision | Consequence |
|---|---|---|
| D-001 | The front end may present a broad catalog of sports and movements, but the first working analysis will support only one concrete action and one action segment. | Catalog entries without implemented analysis must be marked as planned, unavailable, or illustrative. |
| D-002 | The pose/comparison interface will carry raw keypoints plus generic normalized data. | Preserve timestamps and confidence; keep action-specific angles/phases in the comparison/action layer unless explicitly documented. |
| D-003 | Comparison includes direct frame/keypoint comparison, normalized-feature comparison, and temporal sequence alignment. | Implement these as stages; sequence alignment builds on pose/features and does not solve camera-view differences. |
| D-004 | The capture/processing approach is record-then-process; runtime targets will be set after measuring the selected engine on the demo laptop. | Do not promise an unmeasured latency or true live feedback. |
| D-005 | Results should include an overall similarity score and localized joint and/or movement-phase differences, alongside pose visualization. | Exact score formula and correction language depend on the selected action and its rules. |
| D-006 | Earlier draft: no specific action had been selected. Superseded by D-007 for the current prototype. | Keep the action catalog configurable after the first example; do not treat the first action as universal support. |
| D-007 | For the first runnable prototype, use the standing side leg raise with accompanying arm movement shown in `videos/test2/A-标准.mp4` and `videos/test2/B-学员.mp4`. | The initial comparison covers visible shoulders, elbows, wrists, hips, knees and ankles for one complete action segment. |
| D-008 | The first application runs locally on the current Windows computer and accepts two local videos in a browser: reference A and student B. | The server processes both files locally and retains source videos, per-frame MediaPipe JSON and a comparison result under one run directory. |
| D-009 | Reference and student recordings should follow the same camera direction, approximate height and distance, with one person visible. | The first version reports a capture limitation when this assumption is not met; it does not promise arbitrary-viewpoint invariance. |
| D-010 | First-version feedback is relative to the selected reference video and must point to a joint and action-progress segment. | Feedback can say that a joint is higher, lower or shifted relative to the reference; it does not claim a universal correct form or safety advice. |
| D-011 | Use MediaPipe Pose Landmarker for the current prototype after the test2 full-frame run; retain OpenPose as a benchmark and fallback comparison source. | MediaPipe is behind an adapter, and its 33-point schema is not treated as OpenPose BODY_25. |
| D-012 | The current comparison normalizes each frame around the shoulder midpoint and by shoulder width, filters points below visibility/presence 0.5, and uses DTW over valid upper- and lower-body coordinates. | If either clip has under 50% valid normalized frames, or under 50% of aligned rows have at least four paired landmarks, return `insufficient_data` with reasons and no similarity index/findings. These are prototype quality gates, not calibrated accuracy guarantees. |
| D-013 | Each finding must retain the peak aligned frame and timestamp from both clips and let the user seek both videos to that evidence. | A finding can be inspected in the source footage; its clip-progress percentage is not a semantic repetition label. |
| D-014 | Visual inspection of `test2` selects a standing side-leg-raise and arm-raising sequence as the first supported comparison scope. The clips show different people and full-body frontal framing, but differ in duration and repetition timing. | This validates a runnable cross-person example only. Whole-clip DTW cannot confirm that corresponding semantic repetitions match; the report remains relative evidence, not coaching correctness. |
| D-015 | Show a joint finding only when its mean normalized position difference is at least 0.10 shoulder widths. | This temporary noise floor suppresses all findings in the one available same-person A/B repeat pair while retaining the deliberate raised-arm A/D case. It is based on a small sample and must be revisited after fresh-recording acceptance. |

## Current next-work sequence

- 2026-10-02 conversation: make the current report useful and reviewable against real video evidence first. On existing `test2` clips, seven full-pair runs took 15.55–19.11 seconds, so an early-abort precheck is not yet needed solely to save time. This is the next-work order, not a claim that report quality has been validated. See [STATUS.md](STATUS.md).
- Deferred TODO: evaluate camera/viewpoint comparability after full MediaPipe extraction, with a retry-or-continue warning if evidence supports it. Use labelled same-camera, moved-camera and deliberate-motion examples before choosing any threshold; the uncalibrated similarity index alone cannot identify camera error. Longer clips may change the runtime tradeoff.
- Until that TODO is validated, retain the same-direction, similar-height/distance filming instruction and disclose viewpoint uncertainty in reports. Revisit the order if new evidence or a team decision changes the priority.

## Open decisions to resolve before action implementation

1. What additional actions should be supported after the first side leg raise example?
2. What accuracy and waiting-time targets should replace the current measured prototype values?
3. How should the exploratory similarity index be calibrated with multiple labelled examples?
4. What tolerance for camera height, distance and viewpoint should be accepted after validation?
5. Which human reviewer will confirm whether relative findings are useful for the chosen action, and provide a fresh recording beyond the fixed `test2` clips?

## Change log
- 2026-10-02: Initial project scope and team selections recorded.
- 2026-10-02: Added a MediaPipe per-frame JSON exporter for the requested A.mp4 speed comparison. No sampling; CPU, Full model bundle and VIDEO mode are the documented first-run configuration, with IMAGE mode available as a separate experiment. Every frame is retained even with no detected person. This adds an adapter and benchmark preparation only; it does not select the production engine or establish performance/accuracy results. See MEDIAPIPE_EXPORT.md.
- 2026-10-02: Team questionnaire selected a local browser demo with two videos, same-camera capture guidance, relative reference-based feedback and new-video acceptance. Visual inspection identifies a standing side-leg-raise and arm-raising sequence in `test2`; the videos show different participants but are not identical in duration or repetition timing. MediaPipe full-frame processing and DTW comparison ran end to end. Latest `test2` run `203b6025a63a4c1e85711f9608348c63` processed 396 and 298 frames in 19.11 seconds; its 75.4 index remains uncalibrated. Existing test1 controls were reprocessed with MediaPipe: the same-person A/B repeat produced no findings after the 0.10 shoulder-width noise floor; A/C lower-camera placement left one small wrist finding; A/D deliberate arm raise ranked the changed-side wrist first at 0.401. This is exploratory control evidence, not fresh-recording acceptance. Low-coverage unable-to-judge gates and paired evidence timestamps are implemented. Fresh-recording acceptance remains open.
- 2026-10-02: Recorded the current report-first next-work sequence and deferred the camera/viewpoint comparability warning as a separate TODO. An earlier-abort precheck remains optional if future clip lengths justify it. No new detector or report improvement was implemented by this documentation update.
