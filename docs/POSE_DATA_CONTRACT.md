# Pose Data Contract (Draft)

- Status: Draft; engine-neutral interface
- Last updated: 2026-10-02

## 1. Purpose
Define the boundary between pose extraction and movement comparison. The contract must work before the first supported action is selected and must allow the pose engine to change.

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
- The exact normalization reference (body center, torso scale, or another method) is not yet selected; record it in docs/DECISIONS.md before treating normalized values as production data.
- A monocular model's estimated z/world coordinates must not be described as calibrated ground-truth 3D.

## 4. Derived features and action-specific data
- Joint angles, selected keypoint groups, movement phases, and coaching rules belong to the comparison/action layer unless a future engine adapter provides a clearly documented derived field.
- Derived fields must identify the rule/version that produced them.
- The extraction layer must not label an action as correct or incorrect.

## 5. Comparison stages
The selected scope includes all three stages:
1. Direct comparison of corresponding frame/keypoint data as a baseline.
2. Comparison of normalized keypoints and derived features.
3. Temporal alignment of the two sequences to handle different movement speeds.

Temporal alignment does not by itself solve different camera viewpoints. Initial capture is expected to use the same camera setup; exact tolerances remain TBD.

## 6. Example conceptual payload
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

## 7. Failure and confidence handling
- Preserve confidence values through comparison.
- Mark missing or low-confidence keypoints as unavailable for that comparison, or reduce their contribution according to an explicit rule.
- Return a processing/quality status when no usable person or too few required keypoints are detected.
- Do not convert missing data into a zero-valued joint position.