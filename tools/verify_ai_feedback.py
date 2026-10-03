"""Opt-in live checks; never log credentials or raw provider errors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools.ai_feedback import AIConfig, FeedbackError, load_env, request_response, validate_feedback
from tools.compare_mediapipe_sequences import load_sequence
from tools.squat_evidence import build_evidence, evidence_images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float, default=3.6)
    parser.add_argument("--student-end", type=float)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    load_env(root/".env")
    sequences = {}
    for name in ("reference", "student"):
        sequence = load_sequence(args.run_dir/"pose"/name)
        end = args.student_end if name == "student" and args.student_end else args.end
        sequence["frames"] = [f for f in sequence["frames"] if args.start*1000 <= f["timestamp_ms"] <= end*1000]
        sequences[name] = sequence
    evidence = build_evidence(sequences["reference"], sequences["student"])
    print(json.dumps({"evidence_status": evidence["status"], "reasons": evidence["reasons"],
                      "clips": {name: {key: clip.get(key) for key in ("side", "coverage", "foot_coverage")}
                                for name, clip in evidence["clips"].items()},
                      "stages": [{"id": e["id"], "delta": e["student_minus_reference"]}
                                 for e in evidence["evidence"]]}, ensure_ascii=False))
    if not args.live or evidence["status"] != "complete":
        return 0 if evidence["status"] == "complete" else 2
    import cv2
    try:
        images = evidence_images(evidence, args.run_dir/"input/reference.mp4", args.run_dir/"input/student.mp4", cv2)
        config = AIConfig.from_env()
        result = validate_feedback(request_response(config, evidence, images), evidence, config.key)
        print(json.dumps({"ai_status": result["status"], "image_count": len(images),
                          "summary": result["summary"], "suggestions": result["suggestions"]}, ensure_ascii=False))
    except FeedbackError as exc:
        print(json.dumps({"ai_status": "error", "error_code": exc.code}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
