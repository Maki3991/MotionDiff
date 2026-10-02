import tempfile
import unittest
from pathlib import Path

from tools.compare_mediapipe_sequences import compare, write_report


POINTS = {
    "left_ear": (0.46, 0.20), "right_ear": (0.54, 0.20),
    "left_shoulder": (0.40, 0.30), "right_shoulder": (0.60, 0.30),
    "left_elbow": (0.32, 0.40), "right_elbow": (0.68, 0.40),
    "left_wrist": (0.30, 0.50), "right_wrist": (0.70, 0.50),
    "left_hip": (0.43, 0.55), "right_hip": (0.57, 0.55),
    "left_knee": (0.43, 0.75), "right_knee": (0.57, 0.75),
    "left_ankle": (0.42, 0.95), "right_ankle": (0.58, 0.95),
}


def sequence(*, detected=True, shift=(0.0, 0.0)):
    frames = []
    for index in range(5):
        points = []
        if detected:
            sx, sy = shift
            points = [
                {"name": name, "x": x * 1000 + sx, "y": y * 1000 + sy,
                 "visibility": 0.99, "presence": 0.99}
                for name, (x, y) in POINTS.items()
            ]
        frames.append({
            "frame_index": index,
            "timestamp_ms": index * 33.3,
            "status": "ok" if detected else "no_pose",
            "people": 1 if detected else 0,
            "points": {point["name"]: point for point in points},
        })
    return {"frames": frames}


class CompareSequencesTests(unittest.TestCase):
    def test_translation_only_is_normalized_and_comparable(self):
        result = compare(sequence(), sequence(shift=(120, -80)))
        self.assertEqual(result["status"], "complete")
        self.assertAlmostEqual(result["summary"]["mean_position_delta_shoulder_widths"], 0.0, places=6)
        self.assertEqual(result["summary"]["similarity_index"], 100.0)
        self.assertEqual(result["alignment"]["comparable_path_coverage"], 1.0)

    def test_no_pose_returns_explicit_unable_to_judge(self):
        result = compare(sequence(detected=False), sequence())
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["summary"]["similarity_index"])
        self.assertEqual(result["findings"], [])
        self.assertTrue(any("有效姿态帧覆盖" in reason for reason in result["status_reasons"]))
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "comparison.json"
            write_report(result, report)
            self.assertIn("## 无法判断原因", report.with_suffix(".md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
