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
| D-006 | No specific action has been selected yet. | Keep the action catalog and comparison framework configurable; do not hard-code a named action as settled scope. |

## Open decisions to resolve before action implementation

1. Which action and action segment will be the first supported example?
2. Which pose engine will run in the demo: current OpenPose build, MediaPipe, or another candidate? Benchmark on the target laptop first.
3. What normalization formula and stable keypoint naming/mapping will the engine-neutral contract use?
4. What are the camera/framing instructions, maximum clip length, and acceptable post-recording wait time?
5. For the chosen action, what features, temporal alignment settings, score mapping, and localized feedback rules define acceptable performance?

## Change log
- 2026-10-02: Initial project scope and team selections recorded.