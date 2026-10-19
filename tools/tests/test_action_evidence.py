import io
import json
import math
import unittest

from tools.action_config import ACTIONS, PHASE_IDS, catalog_payload, get_action
from tools.action_evidence import build_evidence
from tools.ai_feedback import AIConfig, INSTRUCTIONS, build_instructions, generate_feedback


def make_frame(raw_points, i):
    points = {}
    for side in ("left", "right"):
        for name, (x, y) in raw_points.items():
            points[f"{side}_{name}"] = {"x": x, "y": y,
                                        "visibility": .99 if side == "left" else .3,
                                        "presence": .99}
    return {"frame_index": i, "timestamp_ms": i * 33.33, "people": 1, "points": points}


def deep_knee_bend_sequence(repeats=1):
    """Front-leg dominant lunge/squat geometry: one clear knee-angle dip."""
    frames = []
    for i in range(121 * repeats):
        progress = (i % 121) / 120
        bend = math.sin(math.pi * progress) ** 2
        flex = math.radians(65 * bend)
        ankle = (150, 500)
        knee = (150 + 70 * bend, 500 - 150 * math.cos(flex))
        hip = (knee[0] - 150 * math.sin(flex), knee[1] - 150 * math.cos(flex))
        shoulder = (hip[0] + 80 * bend, hip[1] - 180)
        frames.append(make_frame({"shoulder": shoulder, "hip": hip, "knee": knee, "ankle": ankle,
                                  "heel": (130, 510), "foot_index": (210, 510)}, i))
    return {"frames": frames}


def hip_hinge_sequence():
    """Deadlift geometry: knees nearly fixed, trunk hinges forward and back."""
    frames = []
    for i in range(121):
        hinge = math.sin(math.pi * i / 120) ** 2
        ankle = (150, 500)
        knee = (150, 360)
        hip = (150 - 20 * hinge, 215)
        shoulder = (150 + 150 * hinge, 55)
        frames.append(make_frame({"shoulder": shoulder, "hip": hip, "knee": knee, "ankle": ankle,
                                  "heel": (130, 510), "foot_index": (210, 510)}, i))
    return {"frames": frames}


class ActionConfigTests(unittest.TestCase):
    def test_registry_has_unique_ids_and_five_phases_each(self):
        self.assertEqual(len(ACTIONS), 3)
        for config in ACTIONS.values():
            self.assertEqual([phase_id for phase_id, _ in config.phases], list(PHASE_IDS))
            self.assertTrue(all(label for _, label in config.phases))
        self.assertEqual(ACTIONS["squat"].noun, "深蹲")
        self.assertEqual(ACTIONS["lunge"].noun, "弓步蹲")
        self.assertEqual(ACTIONS["deadlift"].noun, "硬拉")
        self.assertEqual(get_action("lunge").name, "弓步蹲")
        self.assertIsNone(get_action("shooting"))

    def test_catalog_payload_matches_frontend_contract(self):
        payload = catalog_payload()
        self.assertEqual({item["id"] for item in payload}, {"squat", "lunge", "deadlift"})
        for item in payload:
            self.assertIn("capture_hint", item)
            self.assertIn("capture_protocol", item)
            self.assertEqual(item["category"], "strength")


class ConfigDrivenSegmentationTests(unittest.TestCase):
    def test_lunge_labels_and_complete_evidence(self):
        evidence = build_evidence(deep_knee_bend_sequence(), deep_knee_bend_sequence(), ACTIONS["lunge"])
        self.assertEqual(evidence["status"], "complete", evidence["reasons"])
        self.assertEqual(evidence["action"], "lunge")
        labels = [item["phase_label"] for item in evidence["evidence"]]
        self.assertEqual(labels, ["站立准备", "下沉中段", "最低位", "起身中段", "结束站立"])
        bottom = evidence["clips"]["reference"]["windows"]["bottom"]
        self.assertLess(bottom["metrics"]["knee_angle_deg"]["median"], 120)

    def test_deadlift_uses_trunk_inclination_driver(self):
        evidence = build_evidence(hip_hinge_sequence(), hip_hinge_sequence(), ACTIONS["deadlift"])
        self.assertEqual(evidence["status"], "complete", evidence["reasons"])
        self.assertEqual(evidence["action"], "deadlift")
        labels = [item["phase_label"] for item in evidence["evidence"]]
        self.assertEqual(labels, ["直立准备", "下放中段", "最低位", "拉起中段", "直立锁定"])
        windows = evidence["clips"]["reference"]["windows"]
        self.assertGreater(windows["bottom"]["metrics"]["trunk_inclination_deg"]["median"], 30)
        self.assertLess(windows["standing"]["metrics"]["trunk_inclination_deg"]["median"], 10)

    def test_config_gates_segmentation_not_geometry(self):
        # The hinge clip has almost no knee excursion, so the squat config must reject it…
        rejected = build_evidence(hip_hinge_sequence(), hip_hinge_sequence(), ACTIONS["squat"])
        self.assertEqual(rejected["status"], "insufficient_data")
        # …while the deadlift config accepts the same pixels.
        accepted = build_evidence(hip_hinge_sequence(), hip_hinge_sequence(), ACTIONS["deadlift"])
        self.assertEqual(accepted["status"], "complete")

    def test_multiple_reps_rejected_for_new_actions(self):
        for config in (ACTIONS["lunge"], ACTIONS["deadlift"]):
            evidence = build_evidence(deep_knee_bend_sequence(repeats=2), deep_knee_bend_sequence(), config)
            self.assertEqual(evidence["status"], "insufficient_data", config.id)

    def test_measured_difference_surfaces_in_evidence(self):
        student = hip_hinge_sequence()
        for frame in student["frames"]:
            frame["points"]["left_shoulder"]["x"] += 15  # deeper hinge than reference
        evidence = build_evidence(hip_hinge_sequence(), student, ACTIONS["deadlift"])
        self.assertEqual(evidence["status"], "complete")
        bottom = [item for item in evidence["evidence"] if item["id"] == "bottom"][0]
        self.assertGreater(bottom["student_minus_reference"]["trunk_inclination_deg"], 1)


class ActionPromptTests(unittest.TestCase):
    def test_instructions_are_retargeted_per_action(self):
        self.assertEqual(build_instructions(ACTIONS["squat"]), INSTRUCTIONS)
        lunge = build_instructions(ACTIONS["lunge"])
        self.assertIn("弓步蹲", lunge)
        self.assertNotIn("深蹲", lunge)
        deadlift = build_instructions(ACTIONS["deadlift"])
        self.assertIn("硬拉", deadlift)
        self.assertNotIn("深蹲", deadlift)

    def test_feedback_request_uses_action_instructions_and_schema_name(self):
        evidence = build_evidence(deep_knee_bend_sequence(), deep_knee_bend_sequence(), ACTIONS["lunge"])
        received = []
        def opener(request, timeout):
            received.append(json.loads(request.data))
            value = {"summary": "两段动作接近。", "suggestions": []}
            return io.BytesIO(json.dumps({"status": "completed", "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}]}).encode())
        config = AIConfig(True, "secret-test-value", "https://api.example.com/v1", "test")
        result = generate_feedback(config, evidence, lambda: [], opener=opener)
        self.assertEqual(result["status"], "complete")
        self.assertIn("弓步蹲", received[0]["instructions"])
        self.assertNotIn("深蹲", received[0]["instructions"])
        self.assertEqual(received[0]["text"]["format"]["name"], "lunge_feedback")


if __name__ == "__main__":
    unittest.main()
