#!/usr/bin/env python3
"""Build a compact ghost-overlay payload for a MotionDiff run directory.

Reads the two MediaPipe pose frame directories (``pose/reference`` and
``pose/student``) plus ``report/comparison.json`` (which already contains the
DTW ``alignment_rows``), and emits a single JSON document the browser can use
to draw the reference skeleton (the "ghost") semi-transparently on top of the
student video, frame-aligned by the DTW pairing.

Nothing is dropped from the timeline: frames without a person keep
``k: null, a: null`` so the browser can seek by timestamp reliably.

Coordinates are original pixel coordinates from the exporter
(``x = landmark.x * width``); the browser is responsible for scaling them to
the displayed video size. Ghost alignment reuses the project's existing
normalization anchor — shoulder midpoint + shoulder distance — computed here
per frame, so ``compare_mediapipe_sequences.py`` stays untouched.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

FRAME_RE = re.compile(r"_(\d+)_keypoints\.json$")
GHOST_JOINTS = (
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle",
    "left_ear", "right_ear",
)
GHOST_BONES = (
    (0, 1),    # left_shoulder - right_shoulder
    (0, 2), (2, 4),     # left arm
    (1, 3), (3, 5),     # right arm
    (0, 6), (1, 7),     # shoulders to hips
    (6, 7),             # hip line
    (6, 8), (8, 10),    # left leg
    (7, 9), (9, 11),    # right leg
    (12, 13),           # ear line (head hint)
    (12, 0), (13, 1),   # ears to shoulders
)
ANCHOR_QUALITY_THRESHOLD = 0.5
SCHEMA_VERSION = "motiondiff-ghost/1.0"


def finite(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def frame_index_of(path: Path) -> int:
    match = FRAME_RE.search(path.name)
    return int(match.group(1)) if match else 10**12


def point_quality(point: dict | None) -> float:
    if not point:
        return 0.0
    values = [finite(point.get(key)) for key in ("visibility", "presence")]
    values = [value for value in values if value is not None]
    return min(values) if values else 1.0


def load_side(directory: Path) -> dict:
    """One entry per frame file, in frame-index order; missing persons kept."""
    paths = sorted(directory.glob("*_keypoints.json"), key=frame_index_of)
    if not paths:
        raise ValueError(f"No MediaPipe frame JSON files found in {directory}")
    frames = []
    width = height = None
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        width = int(payload.get("image_width") or width or 0) or width
        height = int(payload.get("image_height") or height or 0) or height
        people = payload.get("people") or []
        person = people[0] if people else None
        points = {}
        if person:
            for point in person.get("keypoints", []):
                if point.get("name") in GHOST_JOINTS:
                    points[point["name"]] = point
        keypoints = anchor = None
        if person:
            keypoints = []
            for name in GHOST_JOINTS:
                point = points.get(name)
                x, y = (finite(point.get("x")) if point else None,
                        finite(point.get("y")) if point else None)
                if x is None or y is None:
                    keypoints.append(None)
                else:
                    keypoints.append([round(x, 1), round(y, 1),
                                      round(point_quality(point), 2)])
            left = points.get("left_shoulder")
            right = points.get("right_shoulder")
            if (left and right
                    and point_quality(left) >= ANCHOR_QUALITY_THRESHOLD
                    and point_quality(right) >= ANCHOR_QUALITY_THRESHOLD):
                lx, ly = finite(left.get("x")), finite(left.get("y"))
                rx, ry = finite(right.get("x")), finite(right.get("y"))
                if lx is not None and ly is not None and rx is not None and ry is not None:
                    anchor = [round((lx + rx) / 2, 1), round((ly + ry) / 2, 1),
                              round(math.hypot(lx - rx, ly - ry), 1)]
        frames.append({
            "i": int(payload.get("frame_index", frame_index_of(path))),
            "t": finite(payload.get("timestamp_ms")),
            "k": keypoints,
            "a": anchor,
        })
    return {"width": width, "height": height, "frames": frames}


def build_ghost_payload(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    report_path = run_dir / "report" / "comparison.json"
    if not report_path.is_file():
        raise ValueError(f"Comparison report not found: {report_path}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("alignment_rows") or []
    if not rows:
        raise ValueError("Comparison report contains no alignment_rows; run the comparison first")
    reference = load_side(run_dir / "pose" / "reference")
    student = load_side(run_dir / "pose" / "student")
    ref_by_index = {frame["i"]: frame for frame in reference["frames"]}
    tgt_by_index = {frame["i"]: frame for frame in student["frames"]}
    pairs = []
    for row in rows:
        ref_frame = ref_by_index.get(row.get("reference_frame_index"))
        tgt_frame = tgt_by_index.get(row.get("target_frame_index"))
        if ref_frame is None or tgt_frame is None:
            continue  # defensive: exporter and comparer must agree on indices
        pairs.append([ref_frame["i"], tgt_frame["i"]])
    return {
        "schema_version": SCHEMA_VERSION,
        "joints": list(GHOST_JOINTS),
        "bones": [list(bone) for bone in GHOST_BONES],
        "anchor": {"center": "shoulder midpoint", "scale": "shoulder distance",
                   "quality_threshold": ANCHOR_QUALITY_THRESHOLD},
        "reference": {"width": reference["width"], "height": reference["height"],
                      "frames": reference["frames"]},
        "student": {"width": student["width"], "height": student["height"],
                    "frames": student["frames"]},
        "pairs": pairs,
    }


def main() -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="MotionDiff run directory")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout")
    args = parser.parse_args()
    try:
        payload = build_ghost_payload(args.run_dir)
    except ValueError as exc:
        print(f"ghost payload failed: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output} ({len(text)} bytes)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
