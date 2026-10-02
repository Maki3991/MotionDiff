# MotionDiff Product Requirements (Draft)

- Status: Draft for project-shell implementation
- Last updated: 2026-10-02

## 1. Product goal
Help a participant compare a recorded movement with a prepared reference movement. The system extracts body pose data from both recordings, compares the movement sequences, and presents an overall similarity result with the main joint or movement-phase differences.

## 2. Product shape
The front end may organize a broad catalog of sports and movements, including basketball, football, and fitness. This catalog is a navigation and product-structure goal. It does not mean the first version analyzes all those sports.

The initial implementation will support one concrete action and one action segment. Which action is intentionally TBD. Other entries must be visibly marked as planned, unavailable, or illustrative until their analysis rules exist.

## 3. Intended demo workflow
1. A user selects an available sport, movement, and action segment.
2. The system loads a standard reference video whose pose data has been prepared in advance.
3. A participant records the corresponding movement using the demo camera setup.
4. After recording stops, the system processes the participant video.
5. The comparison module compares raw and normalized pose data and aligns the movement sequences in time.
6. The result view presents the skeleton/pose visualization, an overall similarity score, and localized differences by joint and/or movement phase.

The capture and processing interaction is record-then-process for the initial demo. The maximum clip length and acceptable wait time remain TBD pending runtime benchmarking.

## 4. Requirements

### P0: Framework and first supported action
- Provide a data-driven sport/movement/action catalog.
- Distinguish supported entries from placeholders.
- Provide an end-to-end path for one supported action once the team selects it.
- Keep the pose engine behind an adapter so another engine can replace it without rewriting comparison and result presentation.

### P0: Pose data and comparison
- Preserve per-frame raw keypoints with timestamps and confidence values.
- Provide generic normalized keypoints for comparisons.
- Support direct frame/keypoint comparison, normalized feature comparison, and temporal sequence alignment as stages of the comparison pipeline.
- Allow action-specific rules to select keypoints/features and define how differences map to result messages.
- Treat low-confidence or missing keypoints explicitly; do not silently treat them as correct.

### P0: Result presentation
- Show an overall similarity result.
- Highlight the most relevant joint and/or movement-phase differences.
- Show a pose/skeleton visualization that helps the participant understand the comparison.
- Do not show generic coaching language as validated advice until action-specific rules have been defined and checked.

## 5. Non-goals for the initial demo
- Analyzing every sport or movement shown in the catalog.
- Guaranteeing viewpoint invariance across arbitrary camera positions.
- Claiming true calibrated 3D reconstruction from one ordinary camera.
- Providing a universal exercise or sports-coaching model.
- Promising real-time performance before testing the selected inference engine on the target laptop.

## 6. Open product decisions
See docs/DECISIONS.md. In particular, the supported action, camera capture protocol details, pose engine, normalization formula, score mapping, and performance limits remain undecided or unverified.