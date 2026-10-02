# MotionDiff Agent Collaboration Guide

## Project purpose
MotionDiff is a camera-based movement comparison product. Its interface may list many sports and movements, while the initial working analysis supports only one concrete action and one action segment. The supported action is intentionally undecided.

## Read before changing code
1. Read this file.
2. Read docs/PRD.md.
3. Read docs/POSE_DATA_CONTRACT.md before changing pose extraction, comparison, or persistence.
4. Read docs/DEMO_FLOW_ACCEPTANCE.md before changing capture, processing, or result presentation.
5. Read docs/DECISIONS.md for settled choices and unresolved decisions.

## Shared product boundaries
- Treat the multi-sport catalog as a product/interface structure, not as evidence that every listed movement is analyzable.
- Mark unimplemented movement entries as planned, unavailable, or demo placeholders.
- Keep the pose-estimation engine replaceable behind a stable adapter. OpenPose is available locally; MediaPipe is a candidate to benchmark. Neither engine has been selected as the final runtime.
- The first demo is intended to compare a preprocessed reference movement with a participant recording captured from the same camera setup, then show a score and localized differences.
- Do not claim arbitrary camera-view invariance, calibrated monocular 3D, or reliable coaching advice without implementation and validation evidence.
- Do not silently invent an action, camera protocol, score formula, runtime limit, or correction rule. Record decisions in docs/DECISIONS.md.

## Collaboration rules
- Keep one source of truth in these shared documents; do not create separate conflicting specs for each agent.
- When an implementation changes a product boundary or data shape, update the relevant document in the same change.
- Separate implemented behavior, prototype behavior, and planned behavior in code and documentation.
- Report validation actually performed. Do not describe static review as runtime acceptance.