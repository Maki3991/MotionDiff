import copy
import io
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from tools.ai_feedback import AIConfig, FeedbackError, generate_feedback, load_env, provider_evidence, validate_feedback
from tools.squat_evidence import build_evidence


def squat_sequence(*, mirrored=False, scale=1, missing_foot=False, repeats=1, incomplete=False):
    frames = []
    for i in range(121*repeats):
        progress = (i % 121)/120
        bend = math.sin(math.pi*progress)**2
        flex = math.radians(65*bend)
        ankle = (150, 500)
        knee = (150+70*bend, 500-150*math.cos(flex))
        hip = (knee[0]-150*math.sin(flex), knee[1]-150*math.cos(flex))
        shoulder = (hip[0]+80*bend, hip[1]-180)
        raw = {"shoulder": shoulder, "hip": hip, "knee": knee, "ankle": ankle,
               "heel": (130, 510), "foot_index": (210, 510)}
        points = {}
        for side in ("left", "right"):
            for name, (x, y) in raw.items():
                if missing_foot and name in ("heel", "foot_index"):
                    continue
                points[f"{side}_{name}"] = {"x": scale*(-x if mirrored else x)+500,
                    "y": scale*y+100, "visibility": .99 if side == "left" else .3, "presence": .99}
        frames.append({"frame_index": i, "timestamp_ms": i*33.33, "people": 1, "points": points})
    if incomplete:
        frames = frames[40:]
    return {"frames": frames}


class SquatEvidenceTests(unittest.TestCase):
    def test_geometry_is_scale_and_mirror_invariant(self):
        evidence = build_evidence(squat_sequence(), squat_sequence(mirrored=True, scale=2))
        self.assertEqual(evidence["status"], "complete", evidence["reasons"])
        self.assertEqual(evidence["clips"]["reference"]["side"], "left")
        for e in evidence["evidence"]:
            self.assertTrue(all(abs(v) < .01 for v in e["student_minus_reference"].values()))
        bottom = evidence["clips"]["reference"]["windows"]["bottom"]
        self.assertGreater(bottom["samples"], 3)
        self.assertGreater(bottom["metrics"]["trunk_inclination_deg"]["median"], 20)

    def test_missing_feet_omits_only_knee_trajectory(self):
        evidence = build_evidence(squat_sequence(missing_foot=True), squat_sequence())
        self.assertEqual(evidence["status"], "complete")
        self.assertNotIn("knee_trajectory", evidence["evidence"][2]["available_dimensions"])
        self.assertIn("depth", evidence["evidence"][2]["available_dimensions"])

    def test_multiple_reps_incomplete_and_missing_points_do_not_produce_advice(self):
        for sequence in (squat_sequence(repeats=2), squat_sequence(incomplete=True), {"frames": []}):
            self.assertEqual(build_evidence(sequence, squat_sequence())["status"], "insufficient_data")

    def test_changed_depth_produces_different_measured_evidence(self):
        student = squat_sequence()
        for frame in student["frames"]:
            frame["points"]["left_hip"]["y"] += 20
        evidence = build_evidence(squat_sequence(), student)
        self.assertEqual(evidence["status"], "complete")
        self.assertNotEqual(evidence["evidence"][2]["student_minus_reference"]["thigh_angle_from_horizontal_deg"], 0)

    def test_confidence_selects_the_more_visible_common_side(self):
        sequence = squat_sequence()
        for frame in sequence["frames"]:
            for name, point in frame["points"].items():
                point["visibility"] = .95 if name.startswith("right") else .55
        evidence = build_evidence(sequence, sequence)
        self.assertEqual(evidence["clips"]["reference"]["side"], "right")

    def test_squat_excursion_beats_confidence_on_both_clips(self):
        reference = squat_sequence()
        student = squat_sequence()
        for sequence in (reference, student):
            standing = sequence["frames"][0]["points"]
            for frame in sequence["frames"]:
                for name in ("shoulder", "hip", "knee", "ankle"):
                    point = frame["points"][f"left_{name}"]
                    start = standing[f"left_{name}"]
                    for axis in ("x", "y"):
                        point[axis] = start[axis] + .2 * (point[axis] - start[axis])
                    frame["points"][f"right_{name}"]["visibility"] = .8
                for name in ("heel", "foot_index"):
                    frame["points"][f"right_{name}"]["visibility"] = .8
        evidence = build_evidence(reference, student)
        self.assertEqual(evidence["status"], "complete", evidence["reasons"])
        self.assertEqual(evidence["clips"]["reference"]["side"], "right")
        self.assertEqual(evidence["clips"]["student"]["side"], "right")

    def test_unstable_foot_orientation_does_not_claim_forward_direction(self):
        sequence = squat_sequence()
        for i, frame in enumerate(sequence["frames"]):
            if i % 2:
                frame["points"]["left_heel"], frame["points"]["left_foot_index"] = (
                    frame["points"]["left_foot_index"], frame["points"]["left_heel"])
        evidence = build_evidence(sequence, squat_sequence())
        self.assertEqual(evidence["status"], "complete")
        self.assertTrue(all("knee_trajectory" not in e["available_dimensions"] for e in evidence["evidence"]))


class AIClientTests(unittest.TestCase):
    def setUp(self):
        self.evidence = build_evidence(squat_sequence(), squat_sequence())
        self.config = AIConfig(True, "secret-test-value", "https://api.example.com/v1", "test")
        self.feedback = {"summary": "两段动作接近。", "suggestions": []}

    def test_env_precedence_quotes_and_secret_repr(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"AI_MODEL": "process"}, clear=True):
            path = Path(directory)/".env"
            path.write_text('AI_MODEL=file\nAI_API_KEY="test key"\nAI_ENABLED=true # enabled\n', encoding="utf-8")
            load_env(path)
            self.assertEqual(os.environ["AI_MODEL"], "process")
            self.assertEqual(os.environ["AI_API_KEY"], "test key")
            self.assertTrue(AIConfig.from_env().enabled)
            self.assertNotIn(self.config.key, repr(self.config))

    def test_unknown_or_unavailable_evidence_rejected(self):
        item = {"dimension": "depth", "title": "深度", "observation": "差异", "adjustment": "尝试", "evidence_ids": ["invented"]}
        with self.assertRaises(FeedbackError):
            validate_feedback({"summary": "总结", "suggestions": [item]}, self.evidence)
        item["evidence_ids"] = ["bottom"]
        item["dimension"] = "knee_trajectory"
        evidence = build_evidence(squat_sequence(missing_foot=True), squat_sequence())
        with self.assertRaises(FeedbackError):
            validate_feedback({"summary": "总结", "suggestions": [item]}, evidence)

    def test_internal_height_ratio_is_not_sent_to_provider(self):
        original = copy.deepcopy(self.evidence)
        result = provider_evidence(self.evidence)
        self.assertNotIn("hip_minus_knee_height_femur", json.dumps(result))
        self.assertIn("hip_height_relation", result["evidence"][2]["reference"])
        self.assertEqual(self.evidence, original)

    def test_valid_response_uses_server_evidence_and_no_frontend_key(self):
        received = []
        item = {"dimension": "depth", "title": "深度", "observation": "差异", "adjustment": "尝试", "evidence_ids": ["bottom"]}
        value = {"summary": "总结", "suggestions": [item]}
        def opener(request, timeout):
            received.append(json.loads(request.data))
            return io.BytesIO(json.dumps({"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}]}).encode())
        result = generate_feedback(self.config, self.evidence, lambda: [], opener=opener)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["suggestions"][0]["evidence"][0], self.evidence["evidence"][2])
        self.assertNotIn(self.config.key, json.dumps(result))
        self.assertFalse(received[0]["store"])
        self.assertNotIn(self.config.key, json.dumps(received[0]))

    def test_disabled_and_insufficient_data_do_not_call_provider(self):
        def fail():
            self.fail("Must not request images/API")
        result = generate_feedback(AIConfig(False, "", "", ""), self.evidence, fail)
        self.assertEqual(result["status"], "disabled")
        result = generate_feedback(self.config, build_evidence({"frames": []}, squat_sequence()), fail)
        self.assertEqual(result["status"], "insufficient_data")

    def test_errors_are_sanitized_and_do_not_discard_local_evidence(self):
        original = copy.deepcopy(self.evidence)
        for error, code in ((TimeoutError("secret-test-value"), "timeout"),
                            (URLError(TimeoutError("secret-test-value")), "timeout"),
                            (HTTPError("url", 401, "secret-test-value", {}, None), "authentication"),
                            (URLError("secret-test-value"), "connection")):
            def opener(*args, **kwargs):
                raise error
            result = generate_feedback(self.config, self.evidence, lambda: [], opener=opener)
            self.assertEqual(result["error_code"], code)
            self.assertEqual(result["timeout_seconds"], self.config.timeout)
            self.assertGreaterEqual(result["request_elapsed_seconds"], 0)
            self.assertNotIn(self.config.key, json.dumps(result))
            self.assertEqual(self.evidence, original)
        def malformed(*args, **kwargs):
            return io.BytesIO(b'not json')
        self.assertEqual(generate_feedback(self.config, self.evidence, lambda: [], opener=malformed)["error_code"], "invalid_response")


if __name__ == "__main__":
    unittest.main()
