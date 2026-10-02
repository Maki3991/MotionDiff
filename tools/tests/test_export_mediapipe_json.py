"""Exporter integrity checks with a simulated detector, NOT accuracy/speed tests."""
import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

SCRIPT = Path(__file__).resolve().parents[1] / "export_mediapipe_json.py"
SPEC = importlib.util.spec_from_file_location("exporter", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class FakeCapture:
    def __init__(self, advertised=3):
        self.index = 0
        self.advertised = advertised
        self.released = False

    def isOpened(self):
        return True

    def get(self, key):
        return {"fps": 30, "count": self.advertised, "width": 1920,
                "height": 1080, "msec": (self.index - 1) * 1000 / 30}[key]

    def read(self):
        if self.index == 3:
            return False, None
        self.index += 1
        return True, NS(shape=(1080, 1920, 3))

    def release(self):
        self.released = True


class FakeDetector:
    def __init__(self):
        self.timestamps = []
        self.image_calls = 0
        self.closed = False

    def detect_for_video(self, image, timestamp):
        self.timestamps.append(timestamp)
        return NS(pose_landmarks=[], pose_world_landmarks=[])

    def detect(self, image):
        self.image_calls += 1
        return NS(pose_landmarks=[], pose_world_landmarks=[])

    def close(self):
        self.closed = True


def fake_libraries(advertised=3):
    capture, detector = FakeCapture(advertised), FakeDetector()
    base_options = lambda **kwargs: NS(**kwargs)
    base_options.Delegate = NS(CPU="CPU")
    mp = NS(__version__="simulated-for-tests", __file__=None,
            Image=lambda **kwargs: NS(**kwargs), ImageFormat=NS(SRGB="SRGB"),
            tasks=NS(BaseOptions=base_options, vision=NS(
                PoseLandmarkerOptions=lambda **kwargs: NS(**kwargs),
                PoseLandmarker=NS(create_from_options=lambda options: detector),
                RunningMode=NS(VIDEO="VIDEO", IMAGE="IMAGE"))))
    cv2 = NS(__version__="simulated-for-tests", CAP_PROP_FPS="fps",
             CAP_PROP_FRAME_COUNT="count", CAP_PROP_FRAME_WIDTH="width",
             CAP_PROP_FRAME_HEIGHT="height", CAP_PROP_POS_MSEC="msec",
             COLOR_BGR2RGB="rgb", VideoCapture=lambda path: capture,
             cvtColor=lambda frame, mode: frame)
    return mp, cv2, capture, detector


class ExportIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.args = argparse.Namespace(video=root / "A.mp4", model=root / "model.task",
                                       output_dir=root / "output", running_mode="VIDEO")
        self.args.video.write_bytes(b"simulated input; not a real video")
        self.args.model.write_bytes(b"simulated model; not a real model")

    def test_every_frame_saved_even_when_no_person_is_detected(self):
        mp, cv2, capture, detector = fake_libraries()
        result = exporter.export_video(self.args, mp, cv2)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["json_frames"], 3)
        self.assertEqual(result["frames_without_pose"], 3)
        files = sorted(self.args.output_dir.glob("*.json"))
        self.assertEqual([p.name for p in files], [f"A_{i:012d}_keypoints.json" for i in range(3)])
        for i, path in enumerate(files):
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["frame_index"], i)
            self.assertEqual(payload["people"], [])
            self.assertEqual(payload["status"], "no_pose_detected")
        self.assertEqual(detector.timestamps, [0, 33, 67])
        self.assertTrue(capture.released and detector.closed)

    def test_image_mode_still_processes_every_frame(self):
        self.args.running_mode = "IMAGE"
        mp, cv2, _, detector = fake_libraries()
        result = exporter.export_video(self.args, mp, cv2)
        self.assertEqual(result["json_frames"], 3)
        self.assertEqual(detector.image_calls, 3)
        self.assertEqual(detector.timestamps, [])

    def test_truncated_decode_is_not_reported_as_success(self):
        mp, cv2, capture, detector = fake_libraries(advertised=4)
        with self.assertRaisesRegex(RuntimeError, "Frame-count mismatch"):
            exporter.export_video(self.args, mp, cv2)
        report = json.loads((self.args.output_dir / "_meta/run_summary.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["decoded_frames"], 3)
        self.assertTrue(capture.released and detector.closed)

    def test_inference_failure_marks_partial_output(self):
        mp, cv2, capture, detector = fake_libraries()
        detector.detect_for_video = lambda *unused: (_ for _ in ()).throw(RuntimeError("simulated failure"))
        with self.assertRaisesRegex(RuntimeError, "simulated failure"):
            exporter.export_video(self.args, mp, cv2)
        report = json.loads((self.args.output_dir / "_meta/run_summary.json").read_text())
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["json_frames"], 0)
        self.assertTrue(capture.released and detector.closed)

    def test_existing_output_is_preserved(self):
        self.args.output_dir.mkdir()
        sentinel = self.args.output_dir / "existing.json"
        sentinel.write_text("keep me")
        mp, cv2, _, _ = fake_libraries()
        with self.assertRaisesRegex(ValueError, "nonempty"):
            exporter.export_video(self.args, mp, cv2)
        self.assertEqual(sentinel.read_text(), "keep me")

    def test_coordinates_and_missing_confidence_keep_their_meaning(self):
        point = NS(x=0.25, y=0.5, z=-0.1, visibility=0.9, presence=None)
        result = NS(pose_landmarks=[[point] * 33], pose_world_landmarks=[])
        people = exporter.serialize_people(result, 1920, 1080)
        elbow = people[0]["keypoints"][13]
        self.assertEqual(elbow["name"], "left_elbow")
        self.assertEqual((elbow["x"], elbow["y"]), (480, 540))
        self.assertIsNone(elbow["confidence"])
        self.assertIsNone(elbow["presence"])
        self.assertEqual(elbow["visibility"], 0.9)
        point.x = float("nan")
        serialized = exporter.serialize_people(result, 1920, 1080)
        self.assertIsNone(serialized[0]["keypoints"][0]["x"])
        json.dumps(serialized, allow_nan=False)

    def test_missing_decoder_timestamps_fall_back_without_skipping_frames(self):
        clock = exporter.FrameClock(30)
        self.assertEqual(clock.next(0, 0)[1], 0)
        self.assertEqual(clock.next(1, 0)[1:], (33, "frame_index_over_fps"))
        self.assertEqual(clock.next(2, float("nan"))[1], 67)
        self.assertEqual(clock.fallbacks, 2)

    def test_world_coordinates_are_preserved_and_bad_counts_are_rejected(self):
        point = NS(x=0.25, y=0.5, z=-0.1, visibility=0.9, presence=0.8)
        world = NS(x=0.1, y=0.2, z=-0.3, visibility=None, presence=None)
        result = NS(pose_landmarks=[[point] * 33], pose_world_landmarks=[[world] * 33])
        payload = exporter.serialize_people(result, 1920, 1080)
        self.assertEqual(payload[0]["keypoints"][0]["world"]["z"], -0.3)
        result.pose_landmarks = [[point] * 25]
        with self.assertRaisesRegex(ValueError, "Expected 33"):
            exporter.serialize_people(result, 1920, 1080)


if __name__ == "__main__":
    unittest.main()
