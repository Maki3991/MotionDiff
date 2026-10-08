#!/usr/bin/env python3
"""Build a synthetic demo run with REAL comparison output for the ghost overlay.

No camera needed: writes pose frame JSONs for a reference clip (8 frames) and a
student clip (6 frames, scaled 0.85 and shifted), runs the actual comparer to
produce report/comparison.json, so /api/ghost/<run_id> can serve it.

Usage (from repo root, venv active):

    python app.py --port 8770          # 1. start the app FIRST
    python tools/make_demo_run.py      # 2. then create the demo run
    # curl http://127.0.0.1:8770/api/ghost/a1b2c3d4e5f60718293a4b5c6d7e8f90

IMPORTANT: the app clears orphaned run directories on startup
(see clear_orphaned_runs_on_start in app.py), so recreate the demo run
whenever the server restarts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.compare_mediapipe_sequences import compare, load_sequence, write_report

RUN_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
WIDTH, HEIGHT = 1280, 720

BASE = {
    "left_ear": (500, 150), "right_ear": (620, 150),
    "left_shoulder": (520, 250), "right_shoulder": (640, 250),
    "left_elbow": (430, 350), "right_elbow": (730, 350),
    "left_wrist": (400, 470), "right_wrist": (760, 470),
    "left_hip": (545, 430), "right_hip": (635, 430),
    "left_knee": (530, 560), "right_knee": (650, 560),
    "left_ankle": (520, 690), "right_ankle": (660, 690),
}


def write_side(directory: Path, frames_spec, offset=(0, 0), scale=1.0) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    ox, oy = offset
    for index, timestamp, dy in frames_spec:
        keypoints = []
        for name, (x, y) in BASE.items():
            keypoints.append({"index": 0, "name": name, "x": x * scale + ox,
                              "y": y * scale + oy + dy,
                              "visibility": 0.98, "presence": 0.95})
        payload = {"schema_version": "mediapipe-pose-frame/1.0", "frame_index": index,
                   "timestamp_ms": timestamp, "image_width": WIDTH, "image_height": HEIGHT,
                   "status": "detected",
                   "people": [{"person_index": 0, "keypoints": keypoints}]}
        (directory / f"clip_{index:012d}_keypoints.json").write_text(
            json.dumps(payload), encoding="utf-8")


def main() -> int:
    from app import RUNS_DIR  # reuse the app's runs_dir resolution

    run_dir = RUNS_DIR / RUN_ID
    # Reference: 8 frames, arms raise over time. Student: 6 frames, same motion
    # but 0.85 scale + offset -- exercises the ghost anchor transform.
    ref_spec = [(i, i * 40.0, -i * 8) for i in range(8)]
    tgt_spec = [(i, i * 50.0, -i * 10) for i in range(6)]
    write_side(run_dir / "pose" / "reference", ref_spec)
    write_side(run_dir / "pose" / "student", tgt_spec, offset=(60, 40), scale=0.85)
    (run_dir / "report").mkdir(parents=True, exist_ok=True)
    result = compare(load_sequence(run_dir / "pose" / "reference"),
                     load_sequence(run_dir / "pose" / "student"))
    write_report(result, run_dir / "report" / "comparison.json")
    print(json.dumps({"run_id": RUN_ID, "runs_dir": str(RUNS_DIR),
                      "comparison_status": result["status"],
                      "similarity": result["summary"]["similarity_index"],
                      "path_rows": len(result["alignment_rows"])},
                     ensure_ascii=False))
    print(f"ghost endpoint: /api/ghost/{RUN_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
