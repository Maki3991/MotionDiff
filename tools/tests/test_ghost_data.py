import json
import tempfile
import unittest
from pathlib import Path

from tools.ghost_data import GHOST_BONES, GHOST_JOINTS, build_ghost_payload


WIDTH, HEIGHT = 1280, 720
PIXEL_POINTS = {
    "left_ear": (500, 150), "right_ear": (620, 150),
    "left_shoulder": (520, 250), "right_shoulder": (640, 250),
    "left_elbow": (430, 350), "right_elbow": (730, 350),
    "left_wrist": (400, 470), "right_wrist": (760, 470),
    "left_hip": (545, 430), "right_hip": (635, 430),
    "left_knee": (530, 560), "right_knee": (650, 560),
    "left_ankle": (520, 690), "right_ankle": (660, 690),
}


def frame_payload(index, timestamp, detected=True, shoulder_visibility=0.99):
    keypoints = []
    if detected:
        for name, (x, y) in PIXEL_POINTS.items():
            visibility = shoulder_visibility if name.endswith("shoulder") else 0.95
            keypoints.append({"index": 0, "name": name, "x": x, "y": y,
                              "visibility": visibility, "presence": 0.9})
    return {
        "schema_version": "mediapipe-pose-frame/1.0",
        "frame_index": index,
        "timestamp_ms": timestamp,
        "image_width": WIDTH, "image_height": HEIGHT,
        "status": "detected" if detected else "no_pose_detected",
        "people": [{"person_index": 0, "keypoints": keypoints}] if detected else [],
    }


def write_frames(directory, specs):
    directory.mkdir(parents=True)
    for index, detected in specs:
        payload = frame_payload(index, index * 33.3, detected=detected)
        name = f"clip_{index:012d}_keypoints.json"
        (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def write_report(run_dir, rows):
    report_dir = run_dir / "report"
    report_dir.mkdir(parents=True)
    (report_dir / "comparison.json").write_text(
        json.dumps({"schema_version": "motiondiff-comparison/1.0",
                    "alignment_rows": rows}), encoding="utf-8")


def make_run(rows, ref_specs=((0, True), (1, True), (2, False), (3, True)),
             tgt_specs=((0, True), (1, True), (2, True))):
    temp = tempfile.TemporaryDirectory()
    run_dir = Path(temp.name)
    write_frames(run_dir / "pose" / "reference", ref_specs)
    write_frames(run_dir / "pose" / "student", tgt_specs)
    write_report(run_dir, rows)
    return temp, run_dir


class GhostDataTests(unittest.TestCase):
    def test_payload_structure_anchor_and_pairs(self):
        rows = [
            {"reference_frame_index": 0, "target_frame_index": 0},
            {"reference_frame_index": 1, "target_frame_index": 1},
            {"reference_frame_index": 3, "target_frame_index": 2},
        ]
        temp, run_dir = make_run(rows)
        with temp:
            payload = build_ghost_payload(run_dir)
        self.assertEqual(payload["joints"], list(GHOST_JOINTS))
        self.assertEqual(len(GHOST_JOINTS), 14)
        self.assertIn([0, 1], [list(bone) for bone in GHOST_BONES])
        self.assertEqual(payload["pairs"], [[0, 0], [1, 1], [3, 2]])
        self.assertEqual(payload["reference"]["width"], WIDTH)
        self.assertEqual(payload["student"]["height"], HEIGHT)
        self.assertEqual(len(payload["reference"]["frames"]), 4)
        self.assertEqual(len(payload["student"]["frames"]), 3)

        ref0 = payload["reference"]["frames"][0]
        self.assertEqual(ref0["i"], 0)
        self.assertIsNotNone(ref0["k"])
        # Shoulder anchor: midpoint (580, 250), distance 120.
        self.assertEqual(ref0["a"], [580.0, 250.0, 120.0])
        left_shoulder = ref0["k"][0]
        self.assertEqual(left_shoulder[:2], [520.0, 250.0])

        # No-person frames keep k/a null instead of vanishing from the timeline.
        ref2 = payload["reference"]["frames"][2]
        self.assertIsNone(ref2["k"])
        self.assertIsNone(ref2["a"])
        self.assertEqual(ref2["t"], 2 * 33.3)

    def test_low_quality_shoulders_null_anchor(self):
        temp = tempfile.TemporaryDirectory()
        run_dir = Path(temp.name)
        write_frames(run_dir / "pose" / "reference", [(0, True)])
        write_frames(run_dir / "pose" / "student", [(0, True)])
        # Rewrite the reference frame with weak shoulder confidence.
        ref_frame = json.loads((run_dir / "pose" / "reference" /
                                "clip_000000000000_keypoints.json").read_text(encoding="utf-8"))
        for point in ref_frame["people"][0]["keypoints"]:
            if point["name"] in ("left_shoulder", "right_shoulder"):
                point["visibility"] = 0.1
        (run_dir / "pose" / "reference" /
         "clip_000000000000_keypoints.json").write_text(json.dumps(ref_frame), encoding="utf-8")
        write_report(run_dir, [{"reference_frame_index": 0, "target_frame_index": 0}])
        with temp:
            payload = build_ghost_payload(run_dir)
        self.assertIsNone(payload["reference"]["frames"][0]["a"])

    def test_missing_report_and_empty_rows_raise(self):
        temp = tempfile.TemporaryDirectory()
        run_dir = Path(temp.name)
        write_frames(run_dir / "pose" / "reference", [(0, True)])
        write_frames(run_dir / "pose" / "student", [(0, True)])
        with temp:
            with self.assertRaises(ValueError):
                build_ghost_payload(run_dir)
            write_report(run_dir, [])
            with self.assertRaises(ValueError):
                build_ghost_payload(run_dir)

    def test_rows_with_unknown_frame_index_are_skipped(self):
        rows = [
            {"reference_frame_index": 0, "target_frame_index": 0},
            {"reference_frame_index": 99, "target_frame_index": 99},
        ]
        temp, run_dir = make_run(rows)
        with temp:
            payload = build_ghost_payload(run_dir)
        self.assertEqual(payload["pairs"], [[0, 0]])


if __name__ == "__main__":
    unittest.main()
