# Pose Data Contract

- Status: MediaPipe prototype contract; engine-neutral boundaries retained
- Last updated: 2026-10-03

## 1. Purpose
Define the boundary between pose extraction and movement comparison. Preserve engine output and allow the pose engine to change without treating extracted landmarks as an action judgment.

## 2. Required per-frame fields
A pose sequence should preserve, at minimum:

- timestamp_ms: video-relative frame timestamp.
- frame_index: source frame index when available.
- image_width, image_height: dimensions for interpreting raw image coordinates.
- people[]: detected people for the frame; the first demo expects one participant, but the payload should not assume person index is a stable identity.
- For each person, keypoints[] with:
  - stable semantic name (for example left_knee);
  - raw image-space x, y;
  - detection confidence;
  - normalized x, y when available;
  - optional z or world-coordinate fields only when the engine defines their meaning.

## 3. Raw and normalized data
The selected interface choice is to provide raw keypoints plus generic normalized data.

- Raw coordinates are retained for visualization, debugging, and recalculation.
- Normalized coordinates are intended to reduce nuisance variation such as image size, subject scale, or subject position.
- The current comparison centers each frame on the shoulder midpoint and scales by shoulder-to-shoulder distance. This prototype choice does not guarantee invariance to camera viewpoint or individual body proportions.
- A monocular model's estimated z/world coordinates must not be described as calibrated ground-truth 3D.

## 4. Derived features and action-specific data

- The squat action layer stores `comparison.squat_evidence` and `comparison.ai_feedback`. The evidence layer derives side-view knee angle, trunk inclination, thigh angle, hip/knee height relation and foot direction from named MediaPipe landmarks. It gates incomplete, multiple-repetition and low-coverage inputs before an external request.
- `comparison.ai_feedback` is generated only for `action=squat`. The backend sends derived metrics, quality information and up to four representative evidence images; it does not send source videos, names or paths. The provider must return a strict JSON object with a summary and zero to three suggestions whose evidence IDs are checked server-side. Suggestions are marked `review_status: pending`.
- If AI is disabled, unavailable, times out or returns invalid evidence, the complete local comparison report remains available and the AI section shows a sanitized status. Generic comparison requests do not call the AI provider.
- Joint angles, selected keypoint groups, movement phases, and coaching rules belong to the comparison/action layer unless a future engine adapter provides a clearly documented derived field.
- Derived fields must identify the rule/version that produced them.
- The extraction layer must not label an action as correct or incorrect.

## 5. Comparison stages
The selected scope includes all three stages:
1. Direct comparison of corresponding frame/keypoint data as a baseline.
2. Comparison of normalized keypoints and derived features.
3. Temporal alignment of the two sequences to handle different movement speeds.

Temporal alignment does not by itself solve different camera viewpoints. Initial capture is expected to use the same camera setup; exact tolerances remain TBD.

## 6. Current comparison quality gates

- A keypoint is usable when its available `visibility` and `presence` values are both at least 0.5. Missing values are preserved by extraction; the current comparison rule does not substitute an OpenPose confidence score.
- At least 50% of frames in each clip must have a usable shoulder scale and four or more usable comparison landmarks.
- At least 50% of DTW aligned rows must contain four or more paired landmarks. Otherwise status is `insufficient_data`, the report explains why, and no similarity index or findings are emitted.
- A joint appears as a main finding only when its mean normalized difference reaches 0.10 shoulder widths. This temporary floor suppressed the one available same-person repeat control; it is not a broadly calibrated tolerance.
- These thresholds make missing-data failure explicit. They are not calibrated accuracy limits and do not identify whether both clips show the same semantic action.
- Each finding retains a peak frame index and timestamp from both videos so the UI can seek to the evidence.

## 7. Example conceptual payload
This is illustrative, not a locked serialization format:

~~~json
{
  "schema_version": "0.1",
  "engine": { "name": "TBD", "version": "TBD" },
  "video": { "fps": 30, "width": 1280, "height": 720 },
  "frames": [
    {
      "timestamp_ms": 0,
      "frame_index": 0,
      "people": [
        {
          "keypoints": [
            {
              "name": "left_knee",
              "x": 420.0,
              "y": 510.0,
              "confidence": 0.94,
              "normalized_x": 0.12,
              "normalized_y": 0.31
            }
          ]
        }
      ]
    }
  ]
}
~~~

## 8. Failure and confidence handling
- Preserve confidence values through comparison.
- Mark missing or low-confidence keypoints as unavailable for that comparison, or reduce their contribution according to an explicit rule.
- Return a processing/quality status when no usable person or too few required keypoints are detected.
- Do not convert missing data into a zero-valued joint position.

## 9. Squat evidence payload

`tools/squat_evidence.py` returns a versioned evidence object with `status`, `reasons`, per-clip coverage/selected anatomical side, five phase windows (`standing`, `descent`, `bottom`, `ascent`, `finish`), metric medians/ranges and paired evidence IDs. The supported dimensions are `knee_trajectory`, `depth` and `trunk_angle`; a dimension may be absent when its required landmarks or stable foot direction are unavailable. This is a feature extraction contract, not a correctness classifier.

The provider-facing copy removes internal femur-scale ratios and expresses them as cautious anatomical height relations. Internal evidence is retained in the local JSON report for debugging and review.

## 10. Implemented MediaPipe file adapter (2026-10-02)

`tools/export_mediapipe_json.py` implements the prototype per-frame schema `mediapipe-pose-frame/1.0`. It exports every decoded frame, with an independent run summary under `_meta/`. The engine is still a benchmark candidate.

- Frame fields: `frame_index`, `timestamp_ms`, `timestamp_source`, `inference_timestamp_ms`, `image_width`, `image_height`, `engine`, `source_video`, `status`, `people`.
- Each person has a frame-local `person_index` and 33 semantically named `keypoints`. This index is not a persistent identity.
- Keypoint `x`/`y` are image-space pixels obtained from native normalized coordinates times the decoded image width/height. `normalized_x`/`normalized_y` are MediaPipe image-dimension normalization, NOT body-centred or shoulder-width normalization. Values are preserved without clamping.
- `normalized_z` preserves MediaPipe normalized landmark depth; `world` preserves optional model-estimated x/y/z in metres and any supplied visibility/presence. These are not calibrated ground-truth 3D.
- `visibility` and `presence` are preserved separately. For this adapter, `confidence` is nullable and set to null: MediaPipe does not expose an interchangeable OpenPose joint confidence. No generic detection-confidence score is invented; downstream confidence gates require an explicit adapter-specific rule.
- Missing/nonfinite numeric values become JSON null, not zero. A frame with no detected pose is retained with `people: []` and `status: no_pose_detected`.
- Filename: `<video_stem>_<zero_based_frame_index:012d>_keypoints.json`. Similar names do not imply BODY_25 compatibility. The existing BODY_25-only analysis scripts require a separate adapter before consuming this output.
- Details, environment setup, and timing boundaries: `MEDIAPIPE_EXPORT.md`.
