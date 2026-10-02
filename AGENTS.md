# MotionDiff Agent Collaboration Guide

## Project purpose
MotionDiff is a camera-based movement comparison product. Its initial working analysis supports one concrete action scope: the standing side-leg-raise and arm-raising sequence visible in `videos/test2`. Other sports and actions remain unsupported until implemented and validated.

## Read before changing code
1. Read this file.
2. Read docs/PRD.md.
3. Read docs/POSE_DATA_CONTRACT.md before changing pose extraction, comparison, or persistence.
4. Read docs/DEMO_FLOW_ACCEPTANCE.md before changing capture, processing, or result presentation.
5. Read docs/DECISIONS.md for settled choices and unresolved decisions.

## Shared product boundaries
- Treat the multi-sport catalog as a product/interface structure, not as evidence that every listed movement is analyzable.
- Mark unimplemented movement entries as planned, unavailable, or demo placeholders.
- Keep the pose-estimation engine replaceable behind a stable adapter. MediaPipe Pose Landmarker is selected for the current local prototype; this does not establish it as the final production engine.
- The first demo is intended to compare a preprocessed reference movement with a participant recording captured from the same camera setup, then show a score and localized differences.
- Do not claim arbitrary camera-view invariance, calibrated monocular 3D, or reliable coaching advice without implementation and validation evidence.
- The first capture assumption is a single full-body participant, frontal direction, and similar camera height/distance. Arbitrary viewpoint invariance and semantic action matching are unsupported.
- Treat the similarity index and relative feedback as exploratory. Do not describe the score as pass/fail or feedback as safety/professional advice.
- Keep the fresh-recording acceptance beyond the fixed `test2` clips open until that recording is processed and a human reviewer checks its report. Record changes to action scope, capture protocol, thresholds, or feedback in docs/DECISIONS.md.

## Collaboration rules
- Keep one source of truth in these shared documents; do not create separate conflicting specs for each agent.
- When an implementation changes a product boundary or data shape, update the relevant document in the same change.
- Separate implemented behavior, prototype behavior, and planned behavior in code and documentation.
- Report validation actually performed. Do not describe static review as runtime acceptance.
